"""The python-lint policy's commit check refuses a staged Python file that fails ty or basedpyright."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

from _staged import run_check, stage
from workhorse.testing import make_git_repo

SCRIPT = Path(__file__).resolve().parents[2] / "base-library/library/policies/repo/python-lint/scripts/check_types_staged.py"

NONE_KEY = """\
VALUES: dict[str, str] = {}


def lookup(key: str | None) -> str:
    return VALUES[key]
"""


def _check(root: Path, *pathspecs: str) -> subprocess.CompletedProcess[str]:
    return run_check(SCRIPT, root, *pathspecs)


def test_a_staged_file_with_a_none_key_lookup_is_refused_and_named(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    stage(root, "services/x/actions.py", NONE_KEY)

    ran = _check(root)

    assert ran.returncode == 1
    assert "services/x/actions.py:5" in ran.stderr
    assert "ty" in ran.stderr
    assert "basedpyright" in ran.stderr


def test_a_clean_staged_file_passes(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    stage(root, "lib/typed.py", "def one() -> int:\n    return 1\n")

    assert _check(root).returncode == 0


def test_the_check_reads_the_index_not_the_working_tree(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    stage(root, "lib/typed.py", "def one() -> int:\n    return 1\n")
    _ = (root / "lib/typed.py").write_text(NONE_KEY, encoding="utf-8")
    ran = _check(root)
    assert ran.returncode == 0, ran.stderr


def test_a_file_outside_the_pathspecs_is_not_checked(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    stage(root, "other/a.py", NONE_KEY)
    stage(root, "docs/b.py", "x = 1\n")

    assert _check(root, "docs").returncode == 0


def _load_script() -> Any:
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("check_types_staged_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _site_packages(root: Path) -> Path:
    site = root / ".venv/lib/python3.12/site-packages"
    site.mkdir(parents=True)
    return site


def test_editable_entries_inside_the_repo_become_member_roots(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    (root / "lib").mkdir()
    (root / "pkgs/src").mkdir(parents=True)
    site = _site_packages(root)
    _ = (site / "_editable_impl_lib.pth").write_text(f"{root}/lib\n", encoding="utf-8")
    _ = (site / "_editable_impl_pkgs.pth").write_text(f"# note\nimport os\n{root}/pkgs/src\n", encoding="utf-8")
    _ = (site / "outside.pth").write_text(f"{tmp_path}/elsewhere\n{root}/missing\n", encoding="utf-8")

    roots = _load_script().member_roots(root)

    assert roots == ["lib", "pkgs/src"]


def test_a_repository_without_editable_entries_has_no_member_roots(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")

    assert _load_script().member_roots(root) == []
    assert _load_script().pyright_config(root, [], "pyproject.toml") == ["-p", "pyproject.toml"]


def test_member_roots_reach_basedpyright_through_a_config_in_the_scratch_tree(tmp_path: Path) -> None:
    script = _load_script()
    config = script.pyright_config(tmp_path, ["lib", "pkgs/src"], "pyproject.toml")

    assert config == ["-p", str(tmp_path / "pyrightconfig.json")]
    assert (tmp_path / "pyrightconfig.json").read_text(encoding="utf-8") == (
        '{"extraPaths": ["lib", "pkgs/src"], "extends": "pyproject.toml"}'
    )


def test_the_search_paths_the_repository_configures_stay_ahead_of_the_member_roots(tmp_path: Path) -> None:
    _ = (tmp_path / "pyproject.toml").write_text('[tool.basedpyright]\nextraPaths = ["tools/harness"]\n', encoding="utf-8")

    _ = _load_script().pyright_config(tmp_path, ["lib"], "pyproject.toml")

    assert (tmp_path / "pyrightconfig.json").read_text(encoding="utf-8") == (
        '{"extraPaths": ["tools/harness", "lib"], "extends": "pyproject.toml"}'
    )
