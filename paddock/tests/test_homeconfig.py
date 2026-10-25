"""The home config a run uses: the base, the task's override, and where `artifacts_dir` lands."""

from __future__ import annotations

from pathlib import Path

from paddock import homeconfig


def write_base(tmp_path: Path, body: str) -> Path:
    base = tmp_path / "home-config.toml"
    _ = base.write_text(body, encoding="utf-8")
    return base


def test_a_relative_artifacts_dir_becomes_the_path_inside_the_stage(tmp_path: Path) -> None:
    base = write_base(tmp_path, 'artifacts_dir = "repo"\n')
    stage = tmp_path / "stage"

    dest = homeconfig.materialize(base, {}, tmp_path / "out" / "config.toml", stage=stage)

    assert homeconfig.load(dest)["artifacts_dir"] == str((stage / "repo").resolve())


def test_a_relative_artifacts_dir_in_an_override_is_anchored_too(tmp_path: Path) -> None:
    base = write_base(tmp_path, 'artifacts_dir = "/abs/artifacts"\n')
    stage = tmp_path / "stage"

    dest = homeconfig.materialize(base, {"artifacts_dir": "repo"}, tmp_path / "config.toml", stage=stage)

    assert homeconfig.load(dest)["artifacts_dir"] == str((stage / "repo").resolve())


def test_an_absolute_artifacts_dir_is_kept(tmp_path: Path) -> None:
    base = write_base(tmp_path, 'artifacts_dir = "/abs/artifacts"\n')

    dest = homeconfig.materialize(base, {"other": 1}, tmp_path / "config.toml", stage=tmp_path / "stage")

    assert homeconfig.load(dest)["artifacts_dir"] == "/abs/artifacts"


def test_a_base_with_no_override_and_an_absolute_path_is_copied_byte_for_byte(tmp_path: Path) -> None:
    base = write_base(tmp_path, '# kept\nartifacts_dir   =   "/abs/artifacts"\n')

    dest = homeconfig.materialize(base, {}, tmp_path / "config.toml", stage=tmp_path / "stage")

    assert dest.read_bytes() == base.read_bytes()
