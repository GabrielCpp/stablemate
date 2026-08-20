#!/usr/bin/env python3
"""Guard invariant 1: the coder workflow assumes nothing about where it is deployed.

A prompt that says `make lint`, `go test ./...` or "write a pytest file" has decided, on
behalf of every repo that ever installs this workflow, what its toolchain is. When the repo
disagrees the model does not fail — it half-complies, runs the command that does not exist,
and reports around it. The workflow owns the *contract* (which gates run, what the result
schema is); the repo owns the *body* (what the commands are, what a test looks like here),
declared in `agents.yml` and in the skills it installed.

The rule it enforces, in one line: **a prompt may not say a stack name, and code may not act
on one — but code may explain one.**

- Under `coder/prompts/`, every line of the body counts. A Jinja block whose condition
  dispatches on a service's *type* is exempt: text rendered only for a Go service may say
  `go test`, because the repo's own dispatch is what put it there. Unconditional text may not.
- Under `coder/**/*.py`, only what the interpreter sees counts — string literals and
  identifiers. Comments and docstrings are skipped deliberately: `#: The file that proves the
  init worked (e.g. "go.mod")` documents a *parameter* whose value the repo supplies, and a
  guard that cannot tell that from hard-coding `go.mod` teaches people to stop writing the
  comment rather than to stop hard-coding.
- The token list is `scripts/prompt_agnostic_tokens.txt`. Matching is whole-token and
  case-sensitive, and a name whose bare form is an English word is listed in its command shape
  (`re:\\bmake [a-z][\\w-]*`) rather than as a word this codebase uses in every third sentence.
- `ALLOWLIST` exempts whole files that legitimately know a name, each with the reason it is
  there. A file gets on this list by argument, not by being noisy.

What it cannot see is a stack assumption phrased without any of these words — "run the
standard test command for this project" is invisible to a grep, and stays a review's job.

Run:
    uv run python scripts/check_prompt_agnostic.py
"""

from __future__ import annotations

import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOKENS_FILE = REPO / "scripts" / "prompt_agnostic_tokens.txt"

#: Everything the coder workflow ships as text or code. The prompt bodies a repo may override
#: live in the base library and are not scanned here — those are the repo's to own.
SCANNED_ROOTS = ("workflows/src/workhorse_workflows/coder/",)

#: Files exempt from the sweep, each with the reason. An entry is a claim that this file's job
#: is to know a name, not that removing the name was inconvenient.
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

#: Tokens one file may legitimately say, and why. Narrower than `ALLOWLIST`: the file stays
#: guarded against every *other* stack name, which matters most in the files that already have
#: a reason to name one tool. The reason is always the same shape — this names a tool the
#: workflow itself depends on (`requires:`), not one it assumes the deployment repo has.
FILE_TOKEN_ALLOW: dict[str, tuple[tuple[str, ...], str]] = {
    "workflows/src/workhorse_workflows/coder/prompts/plan-qa.md": (
        ("python", "playwright", "maestro"),
        "ostler's own QA DSL and its `driver` enum — a plan file is a Python module because "
        "ostler executes it, and the driver names are values ostler ships, not stacks a repo "
        "chose",
    ),
    "workflows/src/workhorse_workflows/coder/prompts/setup-fix.md": (
        ("python", "playwright", "maestro", "pip install", "uv tool"),
        "the runner-requirement section repairs the interpreter *this workflow* runs ostler's "
        "QA runner in — which package manager installed it, and which import it must satisfy, "
        "is a fact about the workflow's own process, not about the repo under test",
    ),
    "workflows/src/workhorse_workflows/coder/prompts/repair-qa-plan.md": (
        ("python",),
        "same DSL: the repair prompt shows the plan-file syntax it is repairing",
    ),
}

#: A Jinja condition that dispatches on a service's type. Text inside such a block is the
#: repo's own branch rendering, which is exactly how a stack name is supposed to arrive.
TYPE_CONDITION = re.compile(r"(\btype\b|service_type)")
JINJA_IF = re.compile(r"\{%-?\s*(?P<kind>if|elif)\s+(?P<cond>.*?)-?%\}")
JINJA_ENDIF = re.compile(r"\{%-?\s*endif\s*-?%\}")


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


def _typed_block_lines(text: str) -> set[int]:
    """Lines inside a Jinja block conditioned on a service type — allowed to be specific."""
    inside = False
    depth = 0
    allowed: set[int] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        if inside:
            allowed.add(lineno)
        for match in JINJA_IF.finditer(line):
            if inside:
                if match.group("kind") == "if":
                    depth += 1
            elif TYPE_CONDITION.search(match.group("cond")):
                inside, depth = True, 0
                allowed.add(lineno)
        for _ in JINJA_ENDIF.findall(line):
            if not inside:
                continue
            if depth:
                depth -= 1
            else:
                inside = False
    return allowed


def _executable_lines(text: str) -> dict[int, str]:
    """Python reduced to what the interpreter sees: identifiers and non-docstring literals.

    A docstring is a string that is the whole of an expression statement, which at token level
    is a STRING preceded only by NEWLINE/INDENT/DEDENT and followed by a NEWLINE.
    """
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
            # A string that stands alone as a statement is a docstring; anything else is data.
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
