#!/usr/bin/env python3
"""Guard the "no environment in a workflow" rule."""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from pathlib import Path

CONFIG = ".agent-checks.toml"
TABLE = "check-no-env"

OS_MEMBERS = frozenset(
    {"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"}
)


class _EnvVisitor(ast.NodeVisitor):
    """Collect every environment access in one module."""

    def __init__(self) -> None:
        self.hits: list[tuple[int, str]] = []
        self._bare: set[str] = set()

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "os":
            for alias in node.names:
                if alias.name in OS_MEMBERS:
                    self._bare.add(alias.asname or alias.name)
                    self.hits.append((node.lineno, f"from os import {alias.name}"))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr in OS_MEMBERS
        ):
            self.hits.append((node.lineno, f"os.{node.attr}"))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in self._bare:
            self.hits.append((node.lineno, node.id))
        self.generic_visit(node)


def declarations(root: Path) -> dict:
    """What *root*'s repo declares to this check, from its `.agent-checks.toml`."""
    config = root / CONFIG
    if not config.is_file():
        return {}
    return tomllib.loads(config.read_text(encoding="utf-8")).get(TABLE, {})


def check_no_env(root: Path) -> list[str]:
    """No environment read or write anywhere in the workflow package, bar the allowlist."""
    declared = declarations(root)
    if not (relative := declared.get("package")):
        print(f"ok: no [{TABLE}] package declared in {CONFIG} — nothing to scan")
        return []

    package = root / relative
    if not package.is_dir():
        return [f"{relative} does not exist — the check would pass vacuously"]

    allowed: dict[str, str] = declared.get("allow", {})
    offenders: list[str] = []
    scanned = 0
    for path in sorted(package.rglob("*.py")):
        if path.relative_to(package).as_posix() in allowed:
            continue
        scanned += 1
        visitor = _EnvVisitor()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        rel = path.relative_to(root).as_posix()
        for lineno, spelling in dict.fromkeys(visitor.hits):
            offenders.append(f"{rel}:{lineno}: {spelling}")

    offenders += [
        f"{relative}/{name}: excused in {CONFIG}, but the module no longer exists"
        for name in allowed
        if not (package / name).is_file()
    ]

    if not offenders:
        print(f"ok: no environment access in {scanned} workflow modules")
    return offenders


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help=f"repo holding {CONFIG} (default: cwd)"
    )
    args = parser.parse_args()

    declared = declarations(args.root)
    problems = check_no_env(args.root)
    if not problems:
        return 0
    print("\nFAIL check_no_env:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(
        "\nA workflow's inputs must be arguments or workflow parameters, so the "
        "checkpoint records them and --params can set them. Translate the variable at "
        "the process boundary (workhorse/cli/run.py, workhorse/entrypoint.sh) instead.",
        file=sys.stderr,
    )
    for name, why in declared.get("allow", {}).items():
        print(f"Allowed: {name} — {why.strip()}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
