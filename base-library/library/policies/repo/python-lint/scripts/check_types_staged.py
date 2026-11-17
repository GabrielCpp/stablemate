#!/usr/bin/env python3
"""Refuse a commit that stages a Python file ty or basedpyright rejects under the repository's config.

It exports the index to a scratch tree, so each staged ``.py`` file is judged as the
index holds it and next to the other files the index holds. Both checkers run over the staged files only,
from that tree, under the config it carries. The root's ``.venv`` supplies the third-party imports.
Findings go to stderr.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from check_ruff_staged import _git, refuse, staged_python


def tool_command(root: Path, name: str) -> list[str] | None:
    venv = root / ".venv" / "bin" / name
    if venv.is_file():
        return [str(venv)]
    found = shutil.which(name)
    if found:
        return [found]
    if shutil.which("uv"):
        return ["uv", "run", "--quiet", name]
    return None


def export_index(root: Path, target: Path) -> None:
    subprocess.run(
        ["git", "checkout-index", "-a", f"--prefix={target}/"], cwd=root, capture_output=True, check=True
    )


def run(command: list[str], cwd: Path, name: str, scratch: Path) -> str:
    ran = subprocess.run(command, cwd=cwd, capture_output=True, check=False)
    if ran.returncode == 0:
        return ""
    text = (ran.stdout + ran.stderr).decode("utf-8", errors="replace").replace(f"{scratch}/", "").strip()
    return f"{name}:\n{text}"


def main(argv: list[str]) -> int:
    paths = staged_python(argv)
    if not paths:
        return 0
    root = Path(_git("rev-parse", "--show-toplevel").decode().strip())
    ty = tool_command(root, "ty")
    pyright = tool_command(root, "basedpyright")
    if ty is None or pyright is None:
        print("ty or basedpyright is not installed, so the staged Python files cannot be checked.", file=sys.stderr)
        return 1
    python = ["--python", str(root / ".venv")] if (root / ".venv").is_dir() else []
    config = ["-p", "pyproject.toml"] if (root / "pyproject.toml").is_file() else []
    findings: list[str] = []
    with tempfile.TemporaryDirectory(prefix="staged-types-") as tmp:
        scratch = Path(tmp)
        export_index(root, scratch)
        findings.append(
            run([*ty, "check", "--force-exclude", "--output-format", "concise", *python, *paths], scratch, "ty", scratch)
        )
        findings.append(
            run([*pyright, *config, *(["--pythonpath", str(root / ".venv/bin/python")] if python else []), *paths], scratch, "basedpyright", scratch)
        )
    findings = [found for found in findings if found]
    if not findings:
        return 0
    return refuse("A staged Python file fails the repository's type checks:", findings)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
