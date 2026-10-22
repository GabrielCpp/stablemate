import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parent


def _project(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]


def _members() -> dict[str, dict]:
    workspace = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    projects = [
        _project(ROOT / member / "pyproject.toml")
        for member in workspace["tool"]["uv"]["workspace"]["members"]
    ]
    return {project["name"]: project for project in projects}


def _member_versions() -> dict[str, Version]:
    return {name: Version(project["version"]) for name, project in _members().items()}


def _next_series(version: Version) -> Version:
    if version.major == 0:
        return Version(f"0.{version.minor + 1}.0")
    return Version(f"{version.major + 1}.0.0")


def _pins() -> dict[str, SpecifierSet]:
    pins: dict[str, SpecifierSet] = {}
    for written in _project(PACKAGE / "pyproject.toml")["dependencies"]:
        requirement = Requirement(written)
        pins[requirement.name] = requirement.specifier
    return pins


def test_every_pin_names_a_workspace_member() -> None:
    members = _member_versions()
    assert [name for name in _pins() if name not in members] == []


def test_no_pin_falls_behind_its_member() -> None:
    members = _member_versions()
    stale = {
        name: f"pinned {specifier}, member is {members[name]}"
        for name, specifier in _pins().items()
        if not specifier.contains(members[name], prereleases=True)
        and not specifier.contains(_next_series(members[name]), prereleases=True)
    }
    assert stale == {}, "a member released a new major; run make sync-pins"


def test_every_pinned_command_is_exposed_by_the_umbrella() -> None:
    members = _members()
    wanted = {
        command: target
        for name in _pins()
        for command, target in members[name].get("scripts", {}).items()
    }
    assert _project(PACKAGE / "pyproject.toml")["scripts"] == wanted


def test_the_readme_installs_the_umbrella_by_name() -> None:
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    assert re.search(r"^uv tool install stablemate$", readme, re.MULTILINE)
    assert re.search(r"^pipx install stablemate$", readme, re.MULTILINE)
