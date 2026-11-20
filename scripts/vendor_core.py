#!/usr/bin/env python3
"""Link ``core/stablemate_core`` into each tool that ships it and ``base-library`` into farrier, and stamp each link with its digest."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = ("farrier", "workhorse", "ostler", "paddock", "saddlebag")
DIGEST_NAME = "stablemate_core.sha256"
BASE_TOOL = "farrier"
BASE_DIGEST_NAME = "base_library.sha256"


def source(repo: Path) -> Path:
    return repo / "core" / "stablemate_core"


def destination(repo: Path, tool: str) -> Path:
    return repo / tool / tool / "_vendor" / "stablemate_core"


def base_source(repo: Path) -> Path:
    return repo / "base-library"


def base_destination(repo: Path) -> Path:
    return repo / BASE_TOOL / BASE_TOOL / "_vendor" / "base_library"


DESTINATIONS = tuple(destination(REPO, tool) for tool in TOOLS)

VENDOR_INIT = '"""Shared code: a link to ``core/stablemate_core`` in a checkout, real files in a wheel."""\n'


def _sources(root: Path) -> list[Path]:
    """Every file that makes up the package, relative to its own root, sorted."""
    return sorted(
        p.relative_to(root)
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )


def digest(root: Path) -> str:
    """sha256 over the sorted relative posix path and bytes of every file in the package."""
    hasher = hashlib.sha256()
    for relative in _sources(root):
        hasher.update(relative.as_posix().encode("utf-8") + b"\0")
        hasher.update((root / relative).read_bytes() + b"\0")
    return hasher.hexdigest()


def _link_to(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        shutil.rmtree(link)
    link.symlink_to(os.path.relpath(target, link.parent), target_is_directory=True)


def _write(repo: Path, tool: str) -> None:
    _link_to(destination(repo, tool), source(repo))
    vendor = destination(repo, tool).parent
    (vendor / "__init__.py").write_text(VENDOR_INIT, encoding="utf-8")
    (vendor / DIGEST_NAME).write_text(digest(source(repo)) + "\n", encoding="utf-8")


def _write_base(repo: Path) -> None:
    link = base_destination(repo)
    _link_to(link, base_source(repo))
    (link.parent / BASE_DIGEST_NAME).write_text(digest(base_source(repo)) + "\n", encoding="utf-8")


def _link_problems(repo: Path, tool: str, link: Path, target: Path, stamp: Path, want: str) -> list[str]:
    shown = link.relative_to(repo)
    named = target.relative_to(repo).as_posix()
    if not link.is_symlink():
        return [f"{tool}: {shown} is not a symlink to {named}"]
    if link.resolve() != target.resolve():
        return [f"{tool}: {shown} does not resolve to {named}"]
    if not stamp.is_file():
        return [f"{tool}: {stamp.relative_to(repo)} is missing"]
    if stamp.read_text(encoding="utf-8").strip() != want:
        return [f"{tool}: {stamp.relative_to(repo)} is stale"]
    return []


def _problems(repo: Path, tool: str, want: str) -> list[str]:
    link = destination(repo, tool)
    return _link_problems(repo, tool, link, source(repo), link.parent / DIGEST_NAME, want)


def _base_problems(repo: Path) -> list[str]:
    link = base_destination(repo)
    stamp = link.parent / BASE_DIGEST_NAME
    return _link_problems(repo, BASE_TOOL, link, base_source(repo), stamp, digest(base_source(repo)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report a missing link or a stale digest and exit non-zero instead of writing",
    )
    parser.add_argument("--root", type=Path, default=REPO, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    repo: Path = args.root

    if not source(repo).is_dir():
        print(f"vendor: no source package at {source(repo)}", file=sys.stderr)
        return 1

    if args.check:
        want = digest(source(repo))
        problems = [p for tool in TOOLS for p in _problems(repo, tool, want)]
        problems += _base_problems(repo)
        if problems:
            print("stablemate_core or base-library is not linked or stamped where it ships:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            print("\nEdit core/stablemate_core or base-library, then run: make vendor", file=sys.stderr)
            return 1
        print(f"vendor: {len(TOOLS)} tools link and stamp core/stablemate_core, {BASE_TOOL} links and stamps base-library")
        return 0

    for tool in TOOLS:
        _write(repo, tool)
        print(f"vendor: linked and stamped {destination(repo, tool).relative_to(repo)}")
    _write_base(repo)
    print(f"vendor: linked and stamped {base_destination(repo).relative_to(repo)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
