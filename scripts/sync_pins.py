#!/usr/bin/env python3
"""Widen every pin on a workspace member that its member's version has moved past."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

REPO = Path(__file__).resolve().parent.parent
SUBJECT_LIMIT = 72


@dataclass(frozen=True)
class StalePin:
    pyproject: Path
    name: str
    version: Version
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


def member_versions(root: Path) -> dict[str, Version]:
    return {name: version for name, (_, version) in _members(root).items()}


def _requirements(project: dict) -> list[str]:
    extras = project.get("optional-dependencies", {}).values()
    return [*project.get("dependencies", []), *(r for group in extras for r in group)]


def compatible_range(version: Version) -> str:
    if version.major == 0:
        return f">=0.{version.minor},<0.{version.minor + 1}"
    return f">={version.major},<{version.major + 1}"


def series(version: Version) -> str:
    if version.major == 0:
        return f"0.{version.minor}.x"
    return f"{version.major}.x"


def _next_series(version: Version) -> Version:
    if version.major == 0:
        return Version(f"0.{version.minor + 1}.0")
    return Version(f"{version.major + 1}.0.0")


def _behind(specifier: SpecifierSet, version: Version) -> bool:
    return not specifier.contains(version, prereleases=True) and not specifier.contains(
        _next_series(version), prereleases=True
    )


def _widened(requirement: Requirement, version: Version) -> str:
    extras = f"[{','.join(sorted(requirement.extras))}]" if requirement.extras else ""
    marker = f"; {requirement.marker}".replace('"', "'") if requirement.marker else ""
    return f"{requirement.name}{extras}{compatible_range(version)}{marker}"


def stale_pins(root: Path, versions: dict[str, Version] | None = None) -> list[StalePin]:
    members = _members(root)
    versions = member_versions(root) if versions is None else versions
    stale: list[StalePin] = []
    for pyproject, _ in members.values():
        for written in _requirements(_load(pyproject)["project"]):
            requirement = Requirement(written)
            version = versions.get(canonicalize_name(requirement.name))
            if version is not None and _behind(requirement.specifier, version):
                wanted = _widened(requirement, version)
                stale.append(StalePin(pyproject, requirement.name, version, written, wanted))
    return stale


def sync(root: Path, versions: dict[str, Version] | None = None) -> list[StalePin]:
    stale = stale_pins(root, versions)
    for pin in stale:
        text = pin.pyproject.read_text(encoding="utf-8")
        pin.pyproject.write_text(
            text.replace(f'"{pin.written}"', f'"{pin.wanted}"'), encoding="utf-8"
        )
    return stale


def commit_message(root: Path, pins: list[StalePin]) -> tuple[str, str]:
    scope = pins[0].pyproject.relative_to(root).parts[0]
    allowed = ", ".join(f"{pin.name} {series(pin.version)}" for pin in pins)
    subject = f"fix({scope}): allow {allowed}"
    if len(subject) > SUBJECT_LIMIT:
        subject = f"fix({scope}): allow the new majors of its siblings"
    body = "\n".join(f"{pin.written} -> {pin.wanted}" for pin in pins)
    return subject, body


def commit(root: Path, stale: list[StalePin]) -> list[str]:
    subjects: list[str] = []
    for pyproject, pins in groupby(stale, key=lambda pin: pin.pyproject):
        subject, body = commit_message(root, list(pins))
        subprocess.run(
            ["git", "-C", str(root), "commit", "--only", "-m", subject, "-m", body,
             "--", str(pyproject.relative_to(root))],
            check=True,
        )
        subjects.append(subject)
    return subjects


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="report the stale pins and exit non-zero instead of rewriting them",
    )
    mode.add_argument(
        "--commit",
        action="store_true",
        help="commit each rewritten pyproject as a fix under its own package's scope",
    )
    parser.add_argument(
        "--versions-from",
        type=Path,
        help="take each member's version from this checkout instead of this one",
    )
    args = parser.parse_args()
    versions = member_versions(args.versions_from) if args.versions_from else None

    if args.check:
        stale = stale_pins(REPO, versions)
        for pin in stale:
            print(
                f"{pin.pyproject.relative_to(REPO)}: {pin.written} excludes "
                f"{pin.name} {pin.version}; want {pin.wanted}",
                file=sys.stderr,
            )
        if stale:
            print("\nRun: make sync-pins", file=sys.stderr)
            return 1
        print("sync-pins: no pin on a workspace member falls behind its version")
        return 0

    stale = sync(REPO, versions)
    for pin in stale:
        print(f"sync-pins: {pin.pyproject.relative_to(REPO)}: {pin.written} -> {pin.wanted}")
    if args.commit:
        for subject in commit(REPO, stale):
            print(f"sync-pins: committed {subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
