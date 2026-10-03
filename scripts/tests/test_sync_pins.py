from __future__ import annotations

from pathlib import Path

from packaging.version import Version
from sync_pins import compatible_range, stale_pins, sync


def _workspace(root: Path, members: dict[str, str]) -> Path:
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
