"""Refuse a commit whose subject release-please cannot read.

Runs at git's `commit-msg` stage with the message file as its one argument.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

TYPES = ("feat", "fix", "perf", "refactor", "docs", "test", "build", "ci", "chore", "revert")
DEFAULT_EXTRA_SCOPES = ("deps", "release", "ci")
TOOL_SUBJECTS = ("Merge ", 'Revert "', "fixup! ", "squash! ", "amend! ")
SUBJECT = re.compile(rf"^({'|'.join(TYPES)})(\(([a-z0-9][a-z0-9._-]*)\))?(!)?: (.+)$")
SCISSORS = re.compile(r"^# -+ >8 -+$")


def message_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        if SCISSORS.match(line):
            break
        if not line.startswith("#"):
            lines.append(line)
    while lines and not lines[0].strip():
        lines.pop(0)
    return lines


def tracked_dirs(root: Path) -> list[str] | None:
    result = subprocess.run(
        ("git", "ls-tree", "-d", "--name-only", "HEAD"),
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return [name for name in result.stdout.splitlines() if name and not name.startswith(".")]


def extra_scopes(root: Path) -> tuple[str, ...]:
    manifest = root / "agents.yml"
    if not manifest.is_file():
        return DEFAULT_EXTRA_SCOPES
    for line in manifest.read_text(encoding="utf-8").splitlines():
        key, _, value = line.strip().partition(":")
        if key == "commit_extra_scopes":
            found = tuple(re.findall(r"`([^`]+)`", value))
            return found or DEFAULT_EXTRA_SCOPES
    return DEFAULT_EXTRA_SCOPES


def problem(lines: list[str], dirs: list[str] | None, extras: tuple[str, ...]) -> str | None:
    subject = lines[0] if lines else ""
    if subject.startswith(TOOL_SUBJECTS):
        return None
    if not subject:
        return "empty commit message."
    if len(subject) > 72:
        return f"subject is {len(subject)} characters, over the 72 limit."
    match = SUBJECT.match(subject)
    if not match:
        return "subject is not a Conventional Commit."
    scope, description = match.group(3), match.group(5)
    if scope and dirs and scope not in [*dirs, *extras]:
        return f"'{scope}' is not a known scope."
    if description[0].isupper():
        return "the description must not start with a capital."
    if description.endswith("."):
        return "the description must not end with a period."
    if len(lines) > 1 and lines[1].strip():
        return "leave a blank line between the subject and the body."
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_commit_message.py <message file>", file=sys.stderr)
        return 2
    root = Path(
        subprocess.run(
            ("git", "rev-parse", "--show-toplevel"), capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    lines = message_lines(Path(argv[0]).read_text(encoding="utf-8"))
    dirs = tracked_dirs(root)
    extras = extra_scopes(root)
    found = problem(lines, dirs, extras)
    if found is None:
        return 0
    scopes = [*(dirs or []), *extras]
    print(
        "\n".join([
            f"commit-msg: {found}",
            "",
            f"  subject: {lines[0] if lines else ''}",
            "",
            "Conventional Commits: <type>(<scope>): <lowercase imperative description>",
            f"  types:  {', '.join(TYPES)}",
            f"  scopes: {' '.join(scopes)}  (optional, omit for repo-wide changes)",
            "  feat/fix/perf/refactor release a version; docs/test/build/ci/chore do not.",
        ]),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
