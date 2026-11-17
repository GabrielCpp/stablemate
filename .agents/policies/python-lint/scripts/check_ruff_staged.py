#!/usr/bin/env python3
"""Refuse a commit that stages a Python file the repository's ruff config rejects.

It reads each staged ``.py`` file from the index, limited to the pathspecs given as arguments,
and checks it under the config found from the repository root. Findings go to stderr.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def staged_python(pathspecs: list[str]) -> list[str]:
    out = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR", "--", *pathspecs)
    return [path for path in out.decode("utf-8", errors="replace").split("\0") if path.endswith(".py")]


def ruff_command(root: Path) -> list[str] | None:
    venv = root / ".venv" / "bin" / "ruff"
    if venv.is_file():
        return [str(venv)]
    found = shutil.which("ruff")
    if found:
        return [found]
    if shutil.which("uv"):
        return ["uv", "run", "--quiet", "ruff"]
    return None


def check(root: Path, command: list[str], path: str) -> str:
    source = _git("show", f":{path}")
    ran = subprocess.run(
        [*command, "check", "--force-exclude", "--no-cache", "--output-format", "concise", "--stdin-filename", path, "-"],
        input=source,
        cwd=root,
        capture_output=True,
        check=False,
    )
    if ran.returncode == 0:
        return ""
    return (ran.stdout + ran.stderr).decode("utf-8", errors="replace").strip()


def refuse(header: str, findings: list[str]) -> int:
    print(header, file=sys.stderr)
    for found in findings:
        print(found, file=sys.stderr)
    print("Fix the file, restage it, and commit again.", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    paths = staged_python(argv)
    if not paths:
        return 0
    root = Path(_git("rev-parse", "--show-toplevel").decode().strip())
    command = ruff_command(root)
    if command is None:
        print("ruff is not installed, so the staged Python files cannot be checked.", file=sys.stderr)
        return 1
    findings = [found for path in paths if (found := check(root, command, path))]
    if not findings:
        return 0
    return refuse("A staged Python file fails the repository's ruff config:", findings)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
