#!/usr/bin/env python3
"""Widen every pin on a workspace member that its member's current version falls outside."""

from __future__ import annotations

import argparse
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

REPO = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class StalePin:
    pyproject: Path
    written: str
    wanted: str


def _load(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _members(root: Path) -> dict[str, tuple[Path, Version]]:
    members: dict[str, tuple[Path, Version]] = {}
    for member in _load(root / "pyproject.toml")["tool"]["uv"]["workspace"]["members"]:
        pyproject = root / member / "pyproject.toml"
        project = _load(pyproject)["project"]
        if "version" in project:
            members[canonicalize_name(project["name"])] = (pyproject, Version(project["version"]))
    return members


def _requirements(project: dict) -> list[str]:
    extras = project.get("optional-dependencies", {}).values()
    return [*project.get("dependencies", []), *(r for group in extras for r in group)]


def compatible_range(version: Version) -> str:
    if version.major == 0:
        return f">=0.{version.minor},<0.{version.minor + 1}"
    return f">={version.major},<{version.major + 1}"


def _widened(requirement: Requirement, version: Version) -> str:
    extras = f"[{','.join(sorted(requirement.extras))}]" if requirement.extras else ""
    marker = f"; {requirement.marker}".replace('"', "'") if requirement.marker else ""
    return f"{requirement.name}{extras}{compatible_range(version)}{marker}"


def stale_pins(root: Path) -> list[StalePin]:
    members = _members(root)
    stale: list[StalePin] = []
    for pyproject, _ in members.values():
        for written in _requirements(_load(pyproject)["project"]):
            requirement = Requirement(written)
            target = members.get(canonicalize_name(requirement.name))
            if target is None:
                continue
            version = target[1]
            if not requirement.specifier.contains(version, prereleases=True):
                stale.append(StalePin(pyproject, written, _widened(requirement, version)))
    return stale


def sync(root: Path) -> list[StalePin]:
    stale = stale_pins(root)
    for pin in stale:
        text = pin.pyproject.read_text(encoding="utf-8")
        pin.pyproject.write_text(
            text.replace(f'"{pin.written}"', f'"{pin.wanted}"'), encoding="utf-8"
        )
    return stale


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report the stale pins and exit non-zero instead of rewriting them",
    )
    args = parser.parse_args()

    if args.check:
        stale = stale_pins(REPO)
        for pin in stale:
            print(
                f"{pin.pyproject.relative_to(REPO)}: {pin.written} excludes the member's "
                f"version; want {pin.wanted}",
                file=sys.stderr,
            )
        if stale:
            print("\nRun: make sync-pins", file=sys.stderr)
            return 1
        print("sync-pins: every pin on a workspace member admits its version")
        return 0

    for pin in sync(REPO):
        print(f"sync-pins: {pin.pyproject.relative_to(REPO)}: {pin.written} -> {pin.wanted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
