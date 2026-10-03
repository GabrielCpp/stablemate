import re
import tomllib
from pathlib import Path

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


def _pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for requirement in _project(PACKAGE / "pyproject.toml")["dependencies"]:
        name, separator, version = requirement.partition("==")
        assert separator and re.fullmatch(r"[0-9][0-9A-Za-z.+-]*", version), (
            f"{requirement!r} is not an exact `name==version` pin"
        )
        pins[name] = version
    return pins


def test_every_pin_names_a_workspace_member() -> None:
    members = _member_versions()
    assert [name for name in _pins() if name not in members] == []


def test_every_pin_matches_the_member_version() -> None:
    members = _member_versions()
    stale = {
        name: f"pinned {pinned}, member is {members[name]}"
        for name, pinned in _pins().items()
        if members.get(name) != pinned
    }
    assert stale == {}, (
        "a member released a new version; set the stablemate pin to it in "
        "stablemate/pyproject.toml"
    )


def test_the_readme_install_line_names_every_pinned_distribution() -> None:
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    match = re.search(
        r"uv tool install (\S+) --with stablemate --with-executables-from (\S+)", readme
    )
    assert match is not None
    named = [match.group(1), *match.group(2).split(",")]
    assert sorted(named) == sorted(_pins())
