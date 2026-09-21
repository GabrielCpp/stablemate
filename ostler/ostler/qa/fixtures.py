"""Declared QA fixtures: the named arrangements a plan may ask for, and where they live."""

from __future__ import annotations

import ast
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler import registry
from ostler.qa.outcome import QaOutcome
from ostler.qa.tools import opted_in_tools, qa_block, resolved_commands

DEFAULT_TIMEOUT = 120.0


@dataclass(frozen=True)
class FixtureSpec:
    """One declared app-language fixture, as `qa.fixture(name)` will run it."""

    name: str
    tool: str
    args: tuple[str, ...]
    provides: str
    timeout: float = DEFAULT_TIMEOUT

    def as_context(self) -> dict[str, Any]:
        """The form that crosses into the harness process, JSON-shaped."""
        return {
            "tool": self.tool,
            "args": list(self.args),
            "provides": self.provides,
            "timeout": self.timeout,
        }


_PROVIDES_SEP = "\u2014"

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class FixtureRef:
    """One `fixture:` bullet in the book: the arrangement a claim is documented in."""

    name: str
    args: tuple[str, ...]
    provides: str


@dataclass(frozen=True)
class NoArrangement:
    """A `fixture:` bullet whose value states that this node arranges nothing, and why."""

    reason: str


def parse_bullet(value: str) -> FixtureRef | NoArrangement | str:
    """Parse one `fixture:` bullet, or return the sentence explaining why it is not one."""
    text = " ".join(value.split())
    if not text:
        return "empty"
    if registry.self_declared_empty(text):
        return NoArrangement(reason=text)
    head, _, provides = text.partition(_PROVIDES_SEP)
    try:
        tokens = shlex.split(head.strip())
    except ValueError as exc:
        return f"unbalanced quoting: {exc}"
    if not tokens:
        return "names no fixture"
    name, *args = tokens
    if not _NAME_RE.match(name):
        return (
            f"`{name}` is not a fixture name — it must match the key `agents.yml` declares it "
            f"under (lowercase, digits, `.`, `_`, `-`)"
        )
    return FixtureRef(name=name, args=tuple(args), provides=provides.strip())


def declared(root: Path) -> tuple[dict[str, FixtureSpec], list[str]]:
    """Every fixture this repo declares, plus a message for each entry that is malformed."""
    block = qa_block(root).get("fixtures")
    if block is None:
        return {}, []
    if not isinstance(block, dict):
        return {}, ["`qa: {fixtures:}` must be a mapping of name to fixture declaration"]

    specs: dict[str, FixtureSpec] = {}
    errors: list[str] = []
    for name, entry in block.items():
        if not isinstance(entry, dict):
            errors.append(f"qa fixture {name!r} must be a mapping, not {type(entry).__name__}")
            continue
        tool = entry.get("tool")
        if not isinstance(tool, str) or not tool:
            errors.append(f"qa fixture {name!r} has no `tool:` naming the command that runs it")
            continue
        raw_args = entry.get("args", [])
        if not isinstance(raw_args, list) or not all(isinstance(arg, str) for arg in raw_args):
            errors.append(f"qa fixture {name!r}'s `args:` must be a list of strings")
            continue
        provides = entry.get("provides")
        if not isinstance(provides, str) or not provides.strip():
            errors.append(
                f"qa fixture {name!r} has no `provides:` — say what state it guarantees, "
                "in the same terms a scenario's `preconditions:` are written in"
            )
            continue
        raw_timeout = entry.get("timeout", DEFAULT_TIMEOUT)
        if not isinstance(raw_timeout, (int, float)) or isinstance(raw_timeout, bool):
            errors.append(f"qa fixture {name!r}'s `timeout:` must be a number of seconds")
            continue
        specs[str(name)] = FixtureSpec(
            name=str(name),
            tool=tool,
            args=tuple(str(arg) for arg in raw_args),
            provides=provides.strip(),
            timeout=float(raw_timeout),
        )
    return specs, errors


def _title(name: str) -> str:
    return name.replace("-", " ").replace("_", " ").strip().capitalize()


def migrate(root: Path, out_dir: str, *, cfg: dict[str, Any] | None = None) -> QaOutcome:
    """One-shot, mechanical migration of every `qa: {fixtures:}` entry into a fixture-node file."""
    specs, errors = declared(root)
    if errors:
        return QaOutcome(ok=False, message="\n".join(errors))
    if not specs:
        return QaOutcome(ok=True, message="no qa: {fixtures:} declared — nothing to migrate")

    commands = resolved_commands(root, cfg=cfg)
    unresolved = sorted(name for name, spec in specs.items() if spec.tool not in commands)
    if unresolved:
        return QaOutcome(
            ok=False,
            message="\n".join(
                f"qa fixture {name!r} names tool {specs[name].tool!r}, which is not in this "
                "repo's resolved qa: {tools:} catalog"
                for name in unresolved
            ),
        )

    dest = Path(out_dir)
    if not dest.is_absolute():
        dest = root / dest
    if not dest.resolve().is_relative_to(root.resolve()):
        return QaOutcome(
            ok=False,
            message=f"--in {out_dir!r} resolves outside the repo root {root}",
        )
    collisions = sorted(name for name in specs if (dest / f"{name}.md").exists())
    if collisions:
        return QaOutcome(
            ok=False,
            message=f"already exist, refusing to overwrite: {', '.join(collisions)}",
        )

    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, spec in sorted(specs.items()):
        run = shlex.join([commands[spec.tool], *spec.args])
        title = _title(name)
        body = (
            f"---\ntype: fixture\ntitle: {title}\n---\n"
            f"# {title}\n\n"
            f"<!-- migrated from agents.yml's `qa: {{fixtures:}}` "
            f"— original provides: {spec.provides!r} -->\n\n"
            "## Steps\n\n"
            "### run-it\n\n"
            "- kind: run\n"
            f"- run: {run}\n"
        )
        path = dest / f"{name}.md"
        path.write_text(body, encoding="utf-8")
        written.append(str(path.relative_to(root)))

    owed = "\n".join(
        f"  {path}: `provides:` did not survive — the original sentence is parked in an HTML "
        f"comment at the top of the file; write it out as one child per fact "
        f"(`<key> \u2014 <what it means>`), which is what a scenario's `preconditions:` are "
        f"checked against. Its step is written `kind: run` for the same reason — nothing in "
        f"an `agents.yml` entry says whether the command seeds state, so the migration "
        f"writes the reading that claims nothing"
        for path in written
    )
    return QaOutcome(
        ok=True,
        status="incomplete",
        message=(
            f"migrated {len(written)} qa fixture(s) into {dest.relative_to(root)}, none of them "
            f"complete:\n{owed}"
        ),
        data={"paths": written, "provides_not_migrated": list(written)},
    )


def cmd_migrate(root: Path, out_dir: str, *, cfg: dict[str, Any] | None = None) -> QaOutcome:
    """CLI-shaped wrapper: `migrate`'s errors, plus an on-disk write failure as one more."""
    try:
        return migrate(root, out_dir, cfg=cfg)
    except OSError as exc:
        return QaOutcome(ok=False, message=f"could not write migrated fixture node: {exc}")


def preflight_errors(root: Path) -> list[str]:
    """Every reason this repo's declared fixtures could not be used right now."""
    specs, errors = declared(root)
    opted_in = opted_in_tools(root)
    errors.extend(
        f"qa fixture {spec.name!r} runs tool {spec.tool!r}, which this repo has not opted "
        f"into — add it to `qa: {{tools: [{spec.tool!r}]}}` or point the fixture at a tool "
        "that is already there"
        for spec in specs.values()
        if spec.tool not in opted_in
    )
    return errors


def referenced(plan: Path) -> set[str]:
    """The fixture names one plan asks for, read off its AST."""
    try:
        tree = ast.parse(plan.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()

    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "fixture"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
    return names


def resolved(root: Path) -> dict[str, dict[str, Any]]:
    """`{name: spec}` for every well-formed fixture, in the form the harness receives."""
    specs, _errors = declared(root)
    return {name: spec.as_context() for name, spec in specs.items()}
