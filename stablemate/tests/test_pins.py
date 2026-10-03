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


def _member_versions() -> dict[str, Version]:
    workspace = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    versions: dict[str, Version] = {}
    for member in workspace["tool"]["uv"]["workspace"]["members"]:
        project = _project(ROOT / member / "pyproject.toml")
        versions[project["name"]] = Version(project["version"])
    return versions


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


def test_the_readme_install_line_names_every_pinned_distribution() -> None:
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    match = re.search(
        r"uv tool install (\S+) --with stablemate --with-executables-from (\S+)", readme
    )
    assert match is not None
    named = [match.group(1), *match.group(2).split(",")]
    assert sorted(named) == sorted(_pins())
