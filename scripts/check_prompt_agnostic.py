#!/usr/bin/env python3
"""Guard invariant 1: the coder workflow assumes nothing about where it is deployed."""

from __future__ import annotations

import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

import jinja2

REPO = Path(__file__).resolve().parents[1]
TOKENS_FILE = REPO / "scripts" / "prompt_agnostic_tokens.txt"

SCANNED_ROOTS = ("workflows/src/workhorse_workflows/coder/",)

ALLOWLIST: dict[str, str] = {
    "workflows/src/workhorse_workflows/coder/genesis/flow.py": (
        "genesis scaffolds a repo that does not exist yet, so it is the one lane with no "
        "`agents.yml` to read: its stack knowledge arrives as `--params` and its examples "
        "have to show a real one"
    ),
    "workflows/src/workhorse_workflows/coder/genesis/nodes.py": (
        "same lane: the doctor's warnings name the marker files it looked for, which is the "
        "whole content of the warning"
    ),
    "workflows/src/workhorse_workflows/coder/shared/dev.py": (
        "the documented compat shim: a gate with no `services` entry falls back to "
        "`make <gate>` only when the Makefile really defines that target, so repos that "
        "predate the `services` block keep their gates instead of silently losing them"
    ),
}

FILE_TOKEN_ALLOW: dict[str, tuple[tuple[str, ...], str]] = {
    "workflows/src/workhorse_workflows/coder/qa/prompts/plan-qa.md": (
        ("python", "playwright", "maestro"),
        "ostler's own QA DSL and its `driver` enum — a plan file is a Python module because "
        "ostler executes it, and the driver names are values ostler ships, not stacks a repo "
        "chose",
    ),
    "workflows/src/workhorse_workflows/coder/qa/prompts/setup-fix.md": (
        ("python", "playwright", "maestro", "pip install", "uv tool"),
        "the runner-requirement section repairs the interpreter *this workflow* runs ostler's "
        "QA runner in — which package manager installed it, and which import it must satisfy, "
        "is a fact about the workflow's own process, not about the repo under test",
    ),
    "workflows/src/workhorse_workflows/coder/qa/prompts/repair-qa-plan.md": (
        ("python",),
        "same DSL: the repair prompt shows the plan-file syntax it is repairing",
    ),
}

TYPE_CONDITION = re.compile(r"(\btype\b|service_type)")

_JINJA = jinja2.Environment(autoescape=False)  # noqa: S701 - lexing only, nothing is rendered


def load_patterns() -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for raw in TOKENS_FILE.read_text(encoding="utf-8").splitlines():
        token = raw.strip()
        if not token or token.startswith("#"):
            continue
        if token.startswith("re:"):
            patterns.append(re.compile(token[3:]))
        else:
            patterns.append(re.compile(r"(?<![\w./-])" + token + r"(?![\w-])"))
    return patterns


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", *SCANNED_ROOTS],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO / p for p in out.split("\0") if p]


def _block_tags(text: str) -> list[tuple[str, str, int, int]]:
    """Every `{% ..."""
    tags: list[tuple[str, str, int, int]] = []
    tokens = [tok for tok in _JINJA.lex(text) if tok[1] != "whitespace"]
    index = 0
    while index < len(tokens):
        lineno, kind, _ = tokens[index]
        if kind != "block_begin":
            index += 1
            continue
        parts: list[str] = []
        cursor = index + 1
        while cursor < len(tokens) and tokens[cursor][1] != "block_end":
            parts.append(str(tokens[cursor][2]))
            cursor += 1
        end = tokens[cursor][0] if cursor < len(tokens) else lineno
        tags.append((parts[0] if parts else "", " ".join(parts[1:]), lineno, end))
        index = cursor + 1
    return tags


def _typed_block_lines(text: str) -> set[int]:
    """Lines inside a Jinja block conditioned on a service type — allowed to be specific."""
    try:
        tags = _block_tags(text)
    except jinja2.TemplateSyntaxError:
        return set()
    allowed: set[int] = set()
    start: int | None = None
    depth = 0
    for kind, cond, begin, end in tags:
        if start is None:
            if kind in ("if", "elif") and TYPE_CONDITION.search(cond):
                start, depth = begin, 0
            continue
        if kind == "if":
            depth += 1
        elif kind == "endif":
            if depth:
                depth -= 1
            else:
                allowed.update(range(start, end + 1))
                start = None
    if start is not None:
        allowed.update(range(start, len(text.splitlines()) + 1))
    return allowed


def _executable_lines(text: str) -> dict[int, str]:
    """Python reduced to what the interpreter sees: identifiers and non-docstring literals."""
    kept: dict[int, str] = {}
    previous = tokenize.NEWLINE
    pending: tuple[int, str] | None = None
    try:
        stream = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return {n: line for n, line in enumerate(text.splitlines(), start=1)}
    for tok in stream:
        if tok.type in (tokenize.NL, tokenize.COMMENT):
            continue
        if pending is not None:
            if tok.type != tokenize.NEWLINE:
                lineno, value = pending
                kept[lineno] = kept.get(lineno, "") + " " + value
            pending = None
        if tok.type == tokenize.STRING:
            if previous in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
                pending = (tok.start[0], tok.string)
            else:
                kept[tok.start[0]] = kept.get(tok.start[0], "") + " " + tok.string
        elif tok.type == tokenize.NAME:
            kept[tok.start[0]] = kept.get(tok.start[0], "") + " " + tok.string
        previous = tok.type
    return kept


def _scan(rel: str, lines: dict[int, str], patterns: list[re.Pattern[str]]) -> list[str]:
    allowed = {token.lower() for token in FILE_TOKEN_ALLOW.get(rel, ((), ""))[0]}
    hits: list[str] = []
    for lineno in sorted(lines):
        for pattern in patterns:
            for match in pattern.finditer(lines[lineno]):
                if match.group(0).strip("`").lower() in allowed:
                    continue
                hits.append(f"{rel}:{lineno}: {match.group(0)}")
    return hits


def check_prompt_agnostic() -> list[str]:
    patterns = load_patterns()
    offenders: list[str] = []
    scanned = 0
    for path in sorted(_tracked_files()):
        if not path.is_file() or path.suffix not in (".md", ".py"):
            continue
        rel = path.relative_to(REPO).as_posix()
        if rel in ALLOWLIST:
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".py":
            lines = _executable_lines(text)
        else:
            exempt = _typed_block_lines(text)
            lines = {
                n: line
                for n, line in enumerate(text.splitlines(), start=1)
                if n not in exempt
            }
        offenders.extend(_scan(rel, lines, patterns))
    if not offenders:
        print(f"ok: no stack assumptions in {scanned} files under {', '.join(SCANNED_ROOTS)}")
    return offenders


def main() -> int:
    problems = check_prompt_agnostic()
    if not problems:
        return 0
    print("\nFAIL check_prompt_agnostic:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(
        f"\n{len(problems)} stack assumptions. The workflow owns the contract, the repo owns "
        "the body: the command belongs in `agents.yml`, the how-to in a stack skill, and the "
        "prompt says what must be true rather than which tool makes it true.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
