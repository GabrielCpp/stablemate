#!/usr/bin/env python3
"""Guard the strict scope against a Python file too long to hold in the head."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import strict_scope

REPO = Path(__file__).resolve().parents[1]


def _python_files(repo: Path, roots: tuple[str, ...]) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "-co", "--exclude-standard", "--", *roots],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(path for path in out.split("\0") if path.endswith(".py"))


def scoped_files(repo: Path, scope: strict_scope.StrictScope) -> list[str]:
    return [path for path in _python_files(repo, scope.paths) if (repo / path).is_file()]


def length_problems(repo: Path, scope: strict_scope.StrictScope, files: list[str]) -> list[str]:
    offenders: list[str] = []
    for rel in files:
        count = len((repo / rel).read_text(encoding="utf-8").splitlines())
        if count > scope.max_lines:
            offenders.append(f"{rel}: {count} lines, over the {scope.max_lines}-line limit")
    return offenders


def main() -> int:
    scope = strict_scope.load(REPO)
    files = scoped_files(REPO, scope)
    problems = length_problems(REPO, scope, files)
    if not problems:
        print(f"ok: {len(files)} files under the strict scope, none over {scope.max_lines} lines")
        return 0
    print("\nFAIL check_file_length:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
