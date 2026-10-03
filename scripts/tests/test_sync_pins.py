from __future__ import annotations

from pathlib import Path

from conftest import git
from packaging.version import Version
from sync_pins import commit, compatible_range, member_versions, stale_pins, sync


def _workspace(root: Path, members: dict[str, str]) -> Path:
    root.mkdir(exist_ok=True)
    names = ", ".join(f'"{member}"' for member in members)
    (root / "pyproject.toml").write_text(
        f"[tool.uv.workspace]\nmembers = [{names}]\n", encoding="utf-8"
    )
    for member, body in members.items():
        (root / member).mkdir()
        (root / member / "pyproject.toml").write_text(body, encoding="utf-8")
    return root


def _engine(version: str) -> str:
    return f'[project]\nname = "engine"\nversion = "{version}"\n'


def _flows(requirement: str) -> str:
    return (
        '[project]\nname = "flows"\nversion = "2.0.0"\n'
        f'dependencies = [\n  # the engine\n  "{requirement}",\n  "requests>=2",\n]\n'
    )


def test_a_pin_that_admits_the_member_version_is_left_alone(tmp_path: Path) -> None:
    root = _workspace(tmp_path, {"engine": _engine("3.4.0"), "flows": _flows("engine>=3,<4")})

    assert sync(root) == []
    assert (root / "flows" / "pyproject.toml").read_text(encoding="utf-8") == _flows(
        "engine>=3,<4"
    )


def test_a_major_bump_widens_the_cap_and_keeps_the_rest_of_the_file(tmp_path: Path) -> None:
    root = _workspace(tmp_path, {"engine": _engine("4.0.0"), "flows": _flows("engine>=3,<4")})

    sync(root)

    assert (root / "flows" / "pyproject.toml").read_text(encoding="utf-8") == _flows(
        "engine>=4,<5"
    )


def test_an_exact_pin_becomes_the_major_range(tmp_path: Path) -> None:
    root = _workspace(tmp_path, {"engine": _engine("3.1.0"), "flows": _flows("engine==3.0.0")})

    sync(root)

    assert stale_pins(root) == []
    assert '"engine>=3,<4"' in (root / "flows" / "pyproject.toml").read_text(encoding="utf-8")


def test_extras_and_markers_survive_the_rewrite(tmp_path: Path) -> None:
    root = _workspace(
        tmp_path,
        {
            "engine": _engine("2.0.0"),
            "flows": _flows("engine[qa]>=1,<2; python_version >= '3.12'"),
        },
    )

    sync(root)

    assert (root / "flows" / "pyproject.toml").read_text(encoding="utf-8") == _flows(
        "engine[qa]>=2,<3; python_version >= '3.12'"
    )


def test_an_unconstrained_pin_and_a_foreign_package_are_never_touched(tmp_path: Path) -> None:
    root = _workspace(tmp_path, {"engine": _engine("9.0.0"), "flows": _flows("engine")})

    assert stale_pins(root) == []


def test_a_zero_major_member_is_capped_at_its_minor() -> None:
    assert compatible_range(Version("0.3.2")) == ">=0.3,<0.4"
    assert compatible_range(Version("5.1.0")) == ">=5,<6"


def test_a_pin_ahead_of_its_member_waits_for_the_release(tmp_path: Path) -> None:
    root = _workspace(tmp_path, {"engine": _engine("3.4.0"), "flows": _flows("engine>=4,<5")})

    assert stale_pins(root) == []


def test_a_pin_far_ahead_of_its_member_is_pulled_back(tmp_path: Path) -> None:
    root = _workspace(tmp_path, {"engine": _engine("3.4.0"), "flows": _flows("engine>=5,<6")})

    assert [pin.wanted for pin in stale_pins(root)] == ["engine>=3,<4"]


def test_the_versions_of_another_checkout_drive_the_rewrite(tmp_path: Path) -> None:
    release = _workspace(
        tmp_path / "release",
        {"engine": _engine("4.0.0"), "flows": _flows("engine>=3,<4")},
    )
    main = _workspace(
        tmp_path / "main", {"engine": _engine("3.4.0"), "flows": _flows("engine>=3,<4")}
    )

    sync(main, member_versions(release))

    assert (main / "flows" / "pyproject.toml").read_text(encoding="utf-8") == _flows(
        "engine>=4,<5"
    )
    assert (main / "engine" / "pyproject.toml").read_text(encoding="utf-8") == _engine("3.4.0")


def test_each_rewritten_pyproject_is_a_fix_under_its_own_scope(tmp_path: Path) -> None:
    root = _workspace(
        tmp_path,
        {
            "engine": _engine("3.4.0"),
            "flows": _flows("engine>=3,<4"),
            "umbrella": '[project]\nname = "umbrella"\nversion = "1.0.0"\n'
            'dependencies = ["engine>=3,<4", "flows>=2,<3"]\n',
        },
    )
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "gate")
    git(root, "config", "user.email", "gate@example.com")
    git(root, "config", "core.hooksPath", "/dev/null")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")

    commit(root, sync(root, {"engine": Version("4.0.0"), "flows": Version("3.0.0")}))

    assert git(root, "log", "--format=%s", "-2").splitlines() == [
        "fix(umbrella): allow engine 4.x, flows 3.x",
        "fix(flows): allow engine 4.x",
    ]
    assert git(root, "show", "--format=%b", "--no-patch", "HEAD~1") == (
        "engine>=3,<4 -> engine>=4,<5"
    )
    assert git(root, "status", "--porcelain") == ""
