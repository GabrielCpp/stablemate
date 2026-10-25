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


def test_a_relative_workspace_member_becomes_the_path_inside_the_stage(tmp_path: Path) -> None:
    base = write_base(tmp_path, '[workspaces]\nweb = ["web-app", "api-service"]\n')
    stage = tmp_path / "stage"

    dest = homeconfig.materialize(base, {}, tmp_path / "config.toml", stage=stage)

    workspaces = homeconfig.load(dest)["workspaces"]
    assert workspaces == {"web": [str((stage / "web-app").resolve()), str((stage / "api-service").resolve())]}


def test_a_relative_workspace_table_member_is_anchored_and_keeps_its_other_keys(tmp_path: Path) -> None:
    base = write_base(
        tmp_path,
        '[[workspaces.web]]\npath = "web-app"\nname = "front"\nbranch = "main"\n',
    )
    stage = tmp_path / "stage"

    dest = homeconfig.materialize(base, {}, tmp_path / "config.toml", stage=stage)

    assert homeconfig.load(dest)["workspaces"] == {
        "web": [{"path": str((stage / "web-app").resolve()), "name": "front", "branch": "main"}]
    }


def test_absolute_and_home_workspace_members_are_kept(tmp_path: Path) -> None:
    base = write_base(tmp_path, '[workspaces]\nweb = ["/abs/web-app", "~/api-service"]\n')

    dest = homeconfig.materialize(base, {"other": 1}, tmp_path / "config.toml", stage=tmp_path / "stage")

    assert homeconfig.load(dest)["workspaces"] == {"web": ["/abs/web-app", "~/api-service"]}


def test_a_base_with_a_relative_member_and_no_override_is_rewritten_not_copied(tmp_path: Path) -> None:
    body = '# kept\n[workspaces]\nweb = ["web-app"]\n'
    base = write_base(tmp_path, body)
    stage = tmp_path / "stage"

    dest = homeconfig.materialize(base, {}, tmp_path / "config.toml", stage=stage)

    assert dest.read_bytes() != base.read_bytes()
    assert homeconfig.load(dest)["workspaces"] == {"web": [str((stage / "web-app").resolve())]}
