#!/usr/bin/env python3
"""Copy ``core/stablemate_core`` into each tool that carries it, or check the copies."""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "core" / "stablemate_core"

DESTINATIONS = (
    REPO / "farrier" / "farrier" / "_vendor" / "stablemate_core",
    REPO / "workhorse" / "workhorse" / "_vendor" / "stablemate_core",
    REPO / "ostler" / "ostler" / "_vendor" / "stablemate_core",
)

VENDOR_INIT = '''"""Third-party and shared code copied in, not depended on.

Written by ``make vendor`` from ``core/stablemate_core`` at the repo root — edit that
copy, never this one, or ``make check-vendor`` fails. Why a copy at all, and why it is
safe to have two of them, is in ``core/README.md``.
"""

from __future__ import annotations
'''


def _sources(root: Path) -> list[Path]:
    """Every file that makes up the package, relative to its own root, sorted."""
    return sorted(
        p.relative_to(root)
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )


def _write(destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(SOURCE, destination, ignore=shutil.ignore_patterns("__pycache__"))
    (destination.parent / "__init__.py").write_text(VENDOR_INIT, encoding="utf-8")


def _differences(destination: Path) -> list[str]:
    if not destination.is_dir():
        return [f"{destination.relative_to(REPO)} does not exist"]

    want = _sources(SOURCE)
    have = _sources(destination)
    problems = [f"missing {p}" for p in want if p not in have]
    problems += [f"unexpected {p}" for p in have if p not in want]
    problems += [
        f"differs {p}"
        for p in want
        if p in have and not filecmp.cmp(SOURCE / p, destination / p, shallow=False)
    ]
    return [f"{destination.relative_to(REPO)}: {problem}" for problem in problems]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift and exit non-zero instead of writing the copies",
    )
    args = parser.parse_args()

    if not SOURCE.is_dir():
        print(f"vendor: no source package at {SOURCE}", file=sys.stderr)
        return 1

    if args.check:
        problems = [p for d in DESTINATIONS for p in _differences(d)]
        if problems:
            print("vendored copies of stablemate_core have drifted:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            print("\nEdit core/stablemate_core, then run: make vendor", file=sys.stderr)
            return 1
        print(f"vendor: {len(DESTINATIONS)} copies match core/stablemate_core")
        return 0

    for destination in DESTINATIONS:
        _write(destination)
        print(f"vendor: wrote {destination.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
