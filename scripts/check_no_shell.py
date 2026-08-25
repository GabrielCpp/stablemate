#!/usr/bin/env python3
"""Guard the "no ad-hoc shell scripts" rule. Wired into `make test` and into a Claude hook.

A shell script is the cheapest thing to write and the most expensive thing to own. It has no
test, no type checker, no import graph and no home: `ruff` never reads it, `ty` never reads
it, `make lint` is silent about it, and the next person finds three of them that each do
two-thirds of the same job under names that do not say so. The failure is not that bash is
bad — it is that a `.sh` file is *outside every gate this repo has*, so the discipline that
holds everywhere else stops at its first line.

The rule: a new capability goes into the unified Python CLI — a `scripts/*.py` guard or a
workspace member's own package — where it is imported, linted, typed and testable. Not a new
script beside the last one.

Two enforcement points, one rule, one file:

* ``--hook`` reads a Claude Code ``PreToolUse`` payload on stdin and denies the tool call
  before the file exists, with a reason that says where the code belongs instead. That is the
  point at which the decision is still free.
* the default mode sweeps every **tracked** file, because a hook only ever sees the machine
  it is installed on. A script committed from a clone with no hook configured is in the tree
  forever otherwise.

It catches a `.sh`/`.bash`/`.zsh` path and a shell shebang on an extensionless file — the two
shapes an ad-hoc script actually takes. It cannot catch shell smuggled inside a Python
`subprocess.run(..., shell=True)` string, and it does not try to: that code is at least inside
the linted tree, which is the property the rule is protecting.

`ALLOWED` is not a taste exception. Each entry is a file whose *interface is dictated by
another program* — git execs a hook, Docker execs an entrypoint — where the shell file is the
contract and Python would just be a file the shell script calls.

Run:
    uv run python scripts/check_no_shell.py
    echo '{"tool_name":"Write","tool_input":{"file_path":"x.sh"}}' | python3 scripts/check_no_shell.py --hook
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Suffixes that are a shell script by name.
SHELL_SUFFIXES = (".sh", ".bash", ".zsh", ".ksh", ".fish")

#: A shell shebang, so an extensionless `bin/deploy` is not a way around the suffix list.
SHEBANG = re.compile(r"^#!\s*\S*/(?:env\s+)?(?:ba|z|k|da)?sh\b")

#: Paths where another program dictates the interface, so the shell file *is* the contract.
#: git execs `.githooks/*` directly and farrier rewrites a fenced region inside them; Docker
#: execs the entrypoint as PID 1. Both delegate to Python on their second line — which is the
#: shape the rule is asking for, not an exemption from it.
ALLOWED = frozenset(
    {
        ".githooks/commit-msg",
        ".githooks/pre-commit",
        "ostler/docker/sandbox/entrypoint.sh",
    }
)

#: A Bash tool call that authors a script rather than running one: a redirect or a `tee` into a
#: shell-script path. Running an existing script is not creating one, so `bash x.sh` is fine.
BASH_AUTHORS_SCRIPT = re.compile(
    r"(?:>{1,2}\s*|\btee\s+(?:-\S+\s+)*)\S*\.(?:sh|bash|zsh|ksh|fish)\b"
)

STEER = (
    "This repo does not take ad-hoc shell scripts. Put the capability in the unified Python "
    "CLI instead: a new subcommand or module in the workspace member that owns the concern, "
    "or a `scripts/*.py` guard for a repo-level check — code that ruff lints, ty checks and "
    "pytest can import. Shell is allowed only where another program dictates the interface "
    "(a git hook, a container entrypoint), and those files are already in "
    "`scripts/check_no_shell.py`'s ALLOWED set."
)


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [p for p in out.split("\0") if p]


def _is_shell(rel: str, path: Path) -> str | None:
    """Why `rel` is a shell script, or None. Suffix first — it needs no read."""
    if rel in ALLOWED:
        return None
    if path.suffix in SHELL_SUFFIXES:
        return f"shell suffix {path.suffix}"
    if path.suffix:
        return None
    try:
        first = path.open("r", encoding="utf-8", errors="replace").readline()
    except OSError:
        return None
    return f"shell shebang {first.strip()!r}" if SHEBANG.match(first) else None


def check_no_shell(repo: Path = REPO) -> list[str]:
    offenders: list[str] = []
    scanned = 0
    for rel in sorted(_tracked_files()):
        path = repo / rel
        if not path.is_file():
            continue
        scanned += 1
        reason = _is_shell(rel, path)
        if reason:
            offenders.append(f"{rel}: {reason}")
    if not offenders:
        print(f"ok: no ad-hoc shell scripts in {scanned} tracked files")
    return offenders


def hook_decision(payload: dict[str, object]) -> str | None:
    """The `permissionDecisionReason` for a PreToolUse payload, or None to let it through."""
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    if tool in ("Write", "Edit", "NotebookEdit", "MultiEdit"):
        raw = tool_input.get("file_path")
        if not isinstance(raw, str):
            return None
        rel = _relative(raw)
        if rel in ALLOWED or Path(raw).suffix not in SHELL_SUFFIXES:
            return None
        return f"Refusing to write {raw} — a shell script. {STEER}"
    if tool == "Bash":
        command = tool_input.get("command")
        if isinstance(command, str) and BASH_AUTHORS_SCRIPT.search(command):
            return f"Refusing a Bash call that writes a shell script. {STEER}"
    return None


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
    problems = check_no_shell()
    if not problems:
        return 0
    print("\nFAIL check_no_shell:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(f"\n{STEER}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
