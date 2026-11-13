"""A book that sits in the artifacts folder of a workspace, read and checked from a member repository."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from book_todo import FIXTURE, runtime
from ostler._vendor.stablemate_core import config as core_config
from ostler.book import checkout
from ostler.book.check import source_faults
from ostler.book.service import Service
from ostler.book.sources import missing, stale


def _git(folder: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@example.com", *arguments],
                   check=True, capture_output=True)


def _member(folder: Path) -> Path:
    folder.mkdir(parents=True)
    _git(folder, "init", "--quiet")
    (folder / "README").write_text("x\n")
    _git(folder, "add", "README")
    _git(folder, "commit", "--quiet", "-m", "init")
    return folder


@dataclass(frozen=True)
class Workspace:
    artifacts: Path
    api: Path
    web: Path
    env: dict[str, str]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    api = _member(tmp_path / "code" / "todo-api")
    web = _member(tmp_path / "code" / "todo-web")
    config = tmp_path / "home.toml"
    config.write_text(f'[workspaces]\ntodo = ["{api}", "{web}"]\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    artifacts = Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()
    return Workspace(artifacts=artifacts, api=api, web=web, env=runtime(0))


def _lay_out_book(ws: Workspace) -> None:
    shutil.copytree(FIXTURE / "services", ws.artifacts / "services", ignore=shutil.ignore_patterns("__pycache__"))
    for path in (ws.artifacts / "services").rglob("*.py"):
        text = path.read_text()
        if '"app.py::' in text:
            path.write_text(text.replace('"app.py::', '"repo://todo-api/app.py::'))
    shutil.copy(FIXTURE / "app.py", ws.api / "app.py")
    unrelated = ws.api / "services" / "api"
    unrelated.mkdir(parents=True)
    (unrelated / "__init__.py").write_text("")
    (unrelated / "service.py").write_text("raise RuntimeError('the member repository is not the book')\n")


def _ostler(ws: Workspace, arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    binary = Path(sys.executable).parent / "ostler"
    return subprocess.run([str(binary), *arguments], cwd=cwd, env=ws.env, capture_output=True, text=True, check=False)


def test_book_search_from_a_member_repo_finds_the_artifacts_book(workspace):
    _lay_out_book(workspace)
    done = _ostler(workspace, ["book", "search", "todo"], workspace.api)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "services.api" in done.stdout


def test_book_explain_from_a_member_repo_imports_the_artifacts_book_not_the_members_services_package(workspace):
    _lay_out_book(workspace)
    done = _ostler(workspace, ["book", "explain", "services.api", "AddTodo"], workspace.api)
    assert done.returncode == 0, done.stdout + done.stderr


def test_book_check_from_the_artifacts_folder_runs_there(workspace):
    _lay_out_book(workspace)
    done = subprocess.run([sys.executable, "-m", "ostler.book", "check", "services.api"], cwd=workspace.artifacts,
                          env=workspace.env, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr


class _Cls:
    def __init__(self, *source: str) -> None:
        self.__name__ = "Thing"
        self.source = source


def _service(*source: str) -> Service[Any]:
    return cast("Service[Any]", SimpleNamespace(endpoints=(_Cls(*source),), records=(), app=None))


def test_a_qualified_pointer_to_an_existing_member_file_is_no_finding(workspace):
    assert source_faults(_service("repo://todo-api/README::x"), None) == []


def test_a_qualified_pointer_to_a_missing_member_file_is_a_finding_without_app(workspace):
    found = source_faults(_service("repo://todo-api/gone.py::x"), None)
    assert [f.problem for f in found] == ["source repo://todo-api/gone.py does not exist"]


def test_a_pointer_to_an_unknown_member_is_a_finding(workspace):
    found = source_faults(_service("repo://nowhere/a.py::x"), None)
    assert [f.problem for f in found] == ["source repo://nowhere/a.py names no checkout"]


def test_a_bare_pointer_without_app_is_not_checked(workspace):
    assert missing(_service("gone.py::x"), None) == []


def test_a_bare_pointer_to_a_missing_file_is_a_finding_under_app(workspace):
    assert missing(_service("gone.py::x"), str(workspace.api)) == [("Thing", "gone.py")]


def test_stale_skips_a_pointer_into_another_member_and_says_so(workspace):
    service = _service("repo://todo-api/README::x", "repo://todo-web/README::y", "README::z")
    report = stale(service, str(workspace.api), str(workspace.artifacts))
    assert report.untraced == ["repo://todo-web/README::y"]
    assert report.missing == []


def test_checkout_returns_the_folder_of_a_member(workspace):
    assert checkout("todo-api") == str(workspace.api)


def test_checkout_of_an_unknown_member_names_the_known_ones(workspace):
    with pytest.raises(LookupError, match="todo-api, todo-web"):
        checkout("nowhere")
