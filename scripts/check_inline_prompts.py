#!/usr/bin/env python3
"""Guard the bounds on a prompt written in a state's own source."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import textwrap
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from jinja2 import Environment, TemplateSyntaxError, nodes

from workhorse.references import MANIFEST_HELPERS

REPO = Path(__file__).resolve().parents[1]

LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

MAX_LINES = 40

MAX_CHARS = 2000

BANNED_TAGS = {
    nodes.Include: "include",
    nodes.Extends: "extends",
    nodes.Import: "import",
    nodes.FromImport: "from",
}

COMPOSED = "coder/"

STEER = (
    "An inline prompt is a short fixed turn: no manifest reference, no include, and "
    "a heading on its first line. Everything else belongs in a prompt file under the "
    "workflow's own `prompts/` directory, where `references.py`, the prompt sweeps and "
    "a repo's `.agents/flavors/**` override can all see it."
)


@dataclass(frozen=True)
class Site:
    """One `self.agent(..., label=...)` call, as the source wrote it."""

    where: str
    label: str
    text: str


def _is_test(rel: str) -> bool:
    """Whether `rel` is a test, where a prompt is a fixture rather than a turn a run makes."""
    path = PurePosixPath(rel)
    return "tests" in path.parts or path.name.startswith("test_")


def _tracked_python() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [p for p in out.split("\0") if p and not _is_test(p)]


def _literal(node: ast.expr | None) -> str | None:
    """The string `node` is, or None when the source does not say."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def inline_calls(tree: ast.AST) -> list[ast.Call]:
    """Every `self.agent(...)` in `tree` that carries a `label`."""
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "agent":
            continue
        if not isinstance(func.value, ast.Name) or func.value.id != "self":
            continue
        if _keyword(node, "label") is not None:
            found.append(node)
    return found


def _body_problems(site: Site) -> list[str]:
    """What the guard has to say about one inline body."""
    problems: list[str] = []
    text = site.text
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        problems.append(f"{len(lines)} lines, over the {MAX_LINES}-line bound")
    if len(text) > MAX_CHARS:
        problems.append(f"{len(text)} characters, over the {MAX_CHARS}-character bound")
    first = next((line for line in lines if line.strip()), "")
    if not first.lstrip().startswith("#"):
        problems.append("its first line is not a heading, so the diagram has no label")
    if text.strip().endswith(".md") and not re.search(r"\s", text.strip()):
        problems.append("the text is a path, so `label=` was typed onto a prompt file")
    try:
        parsed = Environment().parse(text)
    except TemplateSyntaxError as exc:
        return [*problems, f"it is not valid Jinja: {exc}"]
    used = sorted(
        node.node.name
        for node in parsed.find_all(nodes.Call)
        if isinstance(node.node, nodes.Name) and node.node.name in MANIFEST_HELPERS
    )
    if used:
        problems.append(
            f"it calls {', '.join(used)}, which only a prompt file's sweep resolves"
        )
    for kind, tag in BANNED_TAGS.items():
        if next(parsed.find_all(kind), None) is not None:
            problems.append(f"it uses {{% {tag} %}}, so its length bound is fiction")
    return problems


def site_problems(sites: list[Site]) -> list[str]:
    """Every rule broken by the inline turns of one file."""
    problems: list[str] = []
    repeated = [
        label for label, n in Counter(site.label for site in sites).items() if n > 1
    ]
    for label in sorted(repeated):
        problems.append(
            f"{sites[0].where}: two turns are labelled {label!r}, so they share a run "
            "directory and an output.json"
        )
    for site in sites:
        if not LABEL_PATTERN.match(site.label):
            problems.append(
                f"{site.where}: label {site.label!r} is not a node id "
                f"({LABEL_PATTERN.pattern})"
            )
        if COMPOSED in site.where:
            problems.append(
                f"{site.where}: the coder workflow's prompts are swept for stack "
                "names, and an inline body escapes that sweep"
            )
        for problem in _body_problems(site):
            problems.append(f"{site.where} ({site.label}): {problem}")
    return problems


def _read(rel: str, source: str) -> tuple[list[Site], list[str]]:
    """The inline turns `source` declares, and what it wrote that no sweep can read."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []
    sites: list[Site] = []
    unreadable: list[str] = []
    for call in inline_calls(tree):
        where = f"{rel}:{call.lineno}"
        label = _literal(_keyword(call, "label"))
        text = _literal(call.args[0]) if call.args else None
        if label is None:
            unreadable.append(f"{where}: the label is not a literal")
            continue
        if text is None:
            unreadable.append(
                f"{where} ({label}): the prompt is not a literal string, so no sweep "
                "in this repo can read it"
            )
            continue
        sites.append(Site(where, label, text))
    return sites, unreadable


def check_inline_prompts(repo: Path = REPO) -> list[str]:
    problems: list[str] = []
    total = 0
    for rel in sorted(_tracked_python()):
        path = repo / rel
        if not path.is_file():
            continue
        sites, unreadable = _read(rel, path.read_text(encoding="utf-8", errors="replace"))
        total += len(sites) + len(unreadable)
        problems.extend(unreadable)
        problems.extend(site_problems(sites))
    if not problems:
        print(f"ok: {total} inline prompts within bounds")
    return problems


def hook_decision(payload: dict[str, object]) -> str | None:
    """The `permissionDecisionReason` for a PreToolUse payload, or None to let it through."""
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict) or tool not in ("Write", "Edit", "MultiEdit"):
        return None
    raw = tool_input.get("file_path")
    if not isinstance(raw, str) or not raw.endswith(".py"):
        return None
    source = tool_input.get("content") or tool_input.get("new_string")
    if not isinstance(source, str):
        return None
    rel = _relative(raw)
    if _is_test(rel):
        return None
    sites, unreadable = _read(rel, textwrap.dedent(source))
    problems = [*unreadable, *site_problems(sites)]
    if not problems:
        return None
    return "Refusing this inline prompt:\n" + "\n".join(f"  {p}" for p in problems) + f"\n\n{STEER}"


def _relative(raw: str) -> str:
    try:
        return Path(raw).resolve().relative_to(REPO).as_posix()
    except ValueError:
        return raw


def _hook() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    reason = hook_decision(payload)
    if reason is None:
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


def main(argv: list[str]) -> int:
    if "--hook" in argv:
        return _hook()
    problems = check_inline_prompts()
    if not problems:
        return 0
    print("\nFAIL check_inline_prompts:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(f"\n{STEER}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
