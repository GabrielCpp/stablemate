import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parent


def _project(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]


def _member_versions() -> dict[str, str]:
    workspace = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    versions: dict[str, str] = {}
    for member in workspace["tool"]["uv"]["workspace"]["members"]:
        project = _project(ROOT / member / "pyproject.toml")
        versions[project["name"]] = project["version"]
    return versions


def _pins() -> dict[str, SpecifierSet]:
    pins: dict[str, SpecifierSet] = {}
    for written in _project(PACKAGE / "pyproject.toml")["dependencies"]:
        requirement = Requirement(written)
        pins[requirement.name] = requirement.specifier
    return pins


def test_every_pin_names_a_workspace_member() -> None:
    members = _member_versions()
    assert [name for name in _pins() if name not in members] == []


def test_every_pin_admits_the_member_version() -> None:
    members = _member_versions()
    stale = {
        name: f"pinned {specifier}, member is {members[name]}"
        for name, specifier in _pins().items()
        if not specifier.contains(members[name], prereleases=True)
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
