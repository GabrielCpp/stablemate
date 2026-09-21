#!/usr/bin/env python3
"""Guard the "no ad-hoc shell scripts" rule."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SHELL_SUFFIXES = (".sh", ".bash", ".zsh", ".ksh", ".fish")

SHELL_INTERPRETERS = frozenset({"sh", "bash", "zsh", "ksh", "dash", "fish"})

CONTROL_TOKENS = frozenset({"|", "||", "&&", ";", "&"})

ALLOWED = frozenset(
    {
        ".githooks/commit-msg",
        ".githooks/pre-commit",
        "ostler/docker/sandbox/entrypoint.sh",
    }
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
    """Why `rel` is a shell script, or None."""
    if rel in ALLOWED:
        return None
    if path.suffix in SHELL_SUFFIXES:
        return f"shell suffix {path.suffix}"
    if path.suffix:
        return None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            first = handle.readline()
    except OSError:
        return None
    return f"shell shebang {first.strip()!r}" if _shebang_names_a_shell(first) else None


def _shebang_names_a_shell(first: str) -> bool:
    """Whether `first` is a shebang naming a shell — read as the line's actual grammar (interpreter path, then arguments), not pattern-matched against its raw text."""
    if not first.startswith("#!"):
        return False
    parts = first[2:].strip().split()
    if parts and Path(parts[0]).name == "env":
        parts = [part for part in parts[1:] if not part.startswith("-")]
    return bool(parts) and Path(parts[0]).name in SHELL_INTERPRETERS


def _bash_writes_a_script(command: str) -> bool:
    """Whether a Bash call authors a script rather than running one: a redirect or a `tee` whose target path has a shell suffix."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    targets: list[str] = []
    tee_arguments = False
    previous = ""
    for token in tokens:
        if previous.endswith(">"):
            targets.append(token)
        elif token.startswith(">"):
            targets.append(token.lstrip(">&"))
        elif token in CONTROL_TOKENS:
            tee_arguments = False
        elif Path(token).name == "tee":
            tee_arguments = True
        elif tee_arguments and not token.startswith("-"):
            targets.append(token)
        previous = token
    return any(Path(target).suffix in SHELL_SUFFIXES for target in targets)


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
        if isinstance(command, str) and _bash_writes_a_script(command):
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
