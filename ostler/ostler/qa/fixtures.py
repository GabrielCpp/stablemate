"""Declared QA fixtures: the named arrangements a plan may ask for, and where they live.

A fixture is the *arrangement* a scenario needs before it can observe anything — three
identities in the auth emulator, a ledger with one claim awaiting a decision, a directory
of files a CLI is pointed at. Until this module existed there was no such concept: an
arrangement was either a compose boot step nothing could name, or a block of Python
copied into every plan that needed it, and the second is how a field came to be spelled
two ways in one repo (`note` for `decision_note`) with no gate able to notice.

Two tiers, split by who owns the code:

- **App-language fixtures** (`qa: {fixtures: {...}}`) run a command the *app* ships, so
  the app's own integration tests and the QA lane arrange state through the same code.
  Drift is impossible by construction rather than by review. This is the tier that
  matters, and the one a fixture should be in unless it cannot be.
- **Python fixture modules** (`qa: {fixture_modules: [...]}`) are for arrangements that
  exist only for QA — signing a token, shaping a request body — and are plain modules
  under `<spec-root>/_fixtures/`, importable by a plan and linted by the *same* AST
  allowlist a plan is. They add no capability; they end triplication.

A fixture entry names a tool from the repo's own `qa: {tools: [...]}` opt-in and nothing
else. That is the containment property and it is checkable without running anything: a
fixture is a *specific invocation* of a command the repo already admitted, never a new
door into the process.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler.qa.tools import opted_in_tools, qa_block

#: Where a repo's Python fixture modules live, relative to the directory holding its
#: specs. A fixed name rather than a configurable path: a plan imports `_fixtures.x`, and
#: an import root that moved per repo would make that spelling a lie in some of them.
FIXTURES_DIRNAME = "_fixtures"

#: The package name a declared fixture module is imported under. Absolute, because
#: `ostler.qa.lint` bans relative imports in plan code and that ban is not being widened
#: for this — the harness puts the spec root on `sys.path` and the import resolves the
#: same way `ostler_qa` does.
FIXTURES_PACKAGE = "_fixtures"

#: Seconds a fixture command may take before its result is a timeout. Generous, because
#: an arrangement is often a container talking to another container, and stingy defaults
#: here produce flaky runs that read as product defects.
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


def declared(root: Path) -> tuple[dict[str, FixtureSpec], list[str]]:
    """Every fixture this repo declares, plus a message for each entry that is malformed.

    A malformed entry is an error rather than a skip. The whole point of declaring a
    fixture is that something checks it, and a declaration silently dropped for a typo in
    its key would be the failure mode this module was written to remove.
    """
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
            # Not decoration. `provides:` is what a scenario's `preconditions:` are checked
            # against, and a fixture that cannot say what state it leaves behind cannot be
            # held to leaving it.
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


def declared_modules(root: Path) -> set[str]:
    """The Python fixture module names a plan in this repo may import.

    A module absent from this list is not importable even if the file exists, which is the
    same posture `tools:` takes: presence on disk is not permission.
    """
    values = qa_block(root).get("fixture_modules", [])
    return {str(value) for value in values} if isinstance(values, list) else set()


def preflight_errors(root: Path, *, spec_root: Path | None = None) -> list[str]:
    """Every reason this repo's declared fixtures could not be used right now.

    Three failures, all static: a malformed declaration, a fixture naming a tool the repo
    never opted into, and a declared module with no file behind it. The second is the
    containment check — it is what keeps `fixtures:` from becoming a second, unwatched
    door onto the process — so it is an error even when the command happens to exist.
    """
    specs, errors = declared(root)
    opted_in = opted_in_tools(root)
    errors.extend(
        f"qa fixture {spec.name!r} runs tool {spec.tool!r}, which this repo has not opted "
        f"into — add it to `qa: {{tools: [{spec.tool!r}]}}` or point the fixture at a tool "
        "that is already there"
        for spec in specs.values()
        if spec.tool not in opted_in
    )
    if spec_root is not None:
        directory = spec_root / FIXTURES_DIRNAME
        errors.extend(
            f"qa fixture module {name!r} is declared but there is no "
            f"{FIXTURES_DIRNAME}/{name}.py under {spec_root}"
            for name in sorted(declared_modules(root))
            if not (directory / f"{name}.py").is_file()
        )
    return errors


def referenced(plan: Path) -> tuple[set[str], set[str]]:
    """`(fixture names, module names)` one plan asks for, read off its AST.

    Read statically rather than by grep, for the same reason `covers=` is: a name built at
    runtime claims nothing a static check could verify, and a caller would rather see none
    than see a fragment of one. An unparseable plan yields nothing — `ostler qa lint` and
    ruff both fail on it first, and reporting it twice in two vocabularies helps nobody.
    """
    try:
        tree = ast.parse(plan.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set(), set()

    names: set[str] = set()
    modules: set[str] = set()
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
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            parts = node.module.split(".")
            if parts[0] == FIXTURES_PACKAGE and len(parts) > 1:
                modules.add(parts[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == FIXTURES_PACKAGE and len(parts) > 1:
                    modules.add(parts[1])
    return names, modules


def resolved(root: Path) -> dict[str, dict[str, Any]]:
    """`{name: spec}` for every well-formed fixture, in the form the harness receives.

    Threaded into the harness subprocess's `context["fixtures"]` beside `context["tools"]`
    — the harness imports only the standard library and cannot read `agents.yml` itself.
    """
    specs, _errors = declared(root)
    return {name: spec.as_context() for name, spec in specs.items()}
