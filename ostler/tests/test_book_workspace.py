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

from book_fakes import git as _git
from book_todo import FIXTURE, runtime
from ostler._vendor.stablemate_core import config as core_config
from ostler.book import checkout
from ostler.book.check import source_faults
from ostler.book import App
from ostler.book.service import Service
from ostler.book.sources import missing, stale


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


def _lay_out_book(ws: Workspace, book: Path | None = None, api: Path | None = None) -> None:
    book = book or ws.artifacts
    api = api or ws.api
    shutil.copytree(FIXTURE / "services", book / "services", ignore=shutil.ignore_patterns("__pycache__"))
    for path in (book / "services").rglob("*.py"):
        text = path.read_text()
        if '"app.py::' in text:
            path.write_text(text.replace('"app.py::', '"repo://todo-api/app.py::'))
    for path in (book / "services").rglob("index.tsv"):
        path.write_text(path.read_text().replace("source: app.py::", "source: repo://todo-api/app.py::"))
    shutil.copy(FIXTURE / "app.py", api / "app.py")
    unrelated = api / "services" / "api"
    unrelated.mkdir(parents=True)
    (unrelated / "__init__.py").write_text("raise RuntimeError('the member repository is not the book')\n")


def _run_worktrees(ws: Workspace, tmp_path: Path, branch: str = "run/book-t") -> tuple[Path, Path]:
    core_config.ensure_artifacts_repo()
    trees = tmp_path / "trees"
    cut: list[Path] = []
    for name, repo in (("artifacts", ws.artifacts), ("todo-api", ws.api)):
        target = trees / f"{name}-{branch.replace('/', '-')}"
        _git(repo, "worktree", "add", "--quiet", "-b", branch, str(target))
        cut.append(target.resolve())
    return cut[0], cut[1]


def _ostler(ws: Workspace, arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    binary = Path(sys.executable).parent / "ostler"
    return subprocess.run([str(binary), *arguments], cwd=cwd, env=ws.env, capture_output=True, text=True, check=False)


def test_book_search_from_a_member_repo_finds_the_artifacts_book(workspace):
    _lay_out_book(workspace)
    done = _ostler(workspace, ["book", "search", "todo", "--service", "services.api"], workspace.api)
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
        self.carries = None


def _service(*source: str) -> Service[Any]:
    return cast("Service[Any]", SimpleNamespace(endpoints=(_Cls(*source),), records=(), screens=(), interactions=(), outside=(), app=None))


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


def test_book_search_from_a_member_worktree_reads_the_artifacts_worktree_books(workspace, tmp_path):
    book, api = _run_worktrees(workspace, tmp_path)
    _lay_out_book(workspace, book, api)
    done = _ostler(workspace, ["book", "search", "todo", "--service", "services.api"], api)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "services.api" in done.stdout


def test_book_check_from_the_artifacts_worktree_runs_there(workspace, tmp_path):
    book, api = _run_worktrees(workspace, tmp_path)
    _lay_out_book(workspace, book, api)
    done = subprocess.run([sys.executable, "-m", "ostler.book", "check", "services.api"], cwd=book,
                          env=workspace.env, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr


def test_checkout_from_a_member_worktree_is_the_member_worktree(workspace, tmp_path, monkeypatch):
    _, api = _run_worktrees(workspace, tmp_path)
    monkeypatch.chdir(api)
    assert checkout("todo-api") == str(api)
    assert checkout("todo-web") == str(workspace.web)


def test_a_pointer_into_a_member_resolves_in_the_member_worktree(workspace, tmp_path):
    _, api = _run_worktrees(workspace, tmp_path)
    (api / "only.py").write_text("x = 1\n")
    assert missing(_service("repo://todo-api/only.py::x"), str(api)) == []
    assert missing(_service("repo://todo-api/only.py::x"), str(workspace.api)) == [("Thing", "repo://todo-api/only.py")]


def test_stale_names_the_member_from_its_worktree(workspace, tmp_path):
    book, api = _run_worktrees(workspace, tmp_path)
    service = _service("repo://todo-api/README::x", "repo://todo-web/README::y", "README::z")
    report = stale(service, str(api), str(book))
    assert report.untraced == ["repo://todo-web/README::y"]
    assert report.missing == []


def _screen_service(*source: str, app: App | None = None) -> Service[Any]:
    screen = _Cls(*source)
    screen.__name__ = "Dashboard"
    return cast("Service[Any]", SimpleNamespace(endpoints=(), records=(), screens=(screen,), interactions=(), outside=(), app=app))


def test_a_screen_whose_source_does_not_exist_is_a_finding_under_app(workspace):
    found = source_faults(_screen_service("web/gone.tsx"), str(workspace.api))
    assert [(f.name, f.problem) for f in found] == [("Dashboard", f"source web/gone.tsx does not exist under {workspace.api}")]


def test_a_screen_with_no_source_is_a_warning_not_a_block(workspace):
    found = source_faults(_screen_service(), None)
    assert [(f.name, f.problem, f.blocks) for f in found] == [("Dashboard", "no source pointer", False)]


def test_stale_lists_a_screen_when_the_file_it_names_changed_since_verified(workspace):
    page = workspace.api / "page.tsx"
    page.write_text("one\n")
    (workspace.artifacts / "VERIFIED").write_text("")
    _git(workspace.api, "add", "page.tsx")
    _git(workspace.api, "commit", "--quiet", "-m", "page")
    verified = subprocess.run(["git", "-C", str(workspace.api), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    (workspace.artifacts / "VERIFIED").write_text(verified)
    page.write_text("two\n")
    _git(workspace.api, "commit", "--quiet", "-am", "edit")
    service = _screen_service("page.tsx", app=App(roots=(".",), verified="VERIFIED", ignore=()))
    report = stale(service, str(workspace.api), str(workspace.artifacts))
    assert list(report.stale) == ["Dashboard"]
    assert report.unnamed == {}


def _commit_page(ws: Workspace, text: str) -> str:
    (ws.api / "page.tsx").write_text(text)
    _git(ws.api, "add", "page.tsx")
    _git(ws.api, "commit", "--quiet", "-m", "page")
    return subprocess.run(["git", "-C", str(ws.api), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()


def test_stale_since_a_commit_lists_what_changed_after_it_in_a_book_with_no_verified_commit(workspace):
    base = _commit_page(workspace, "one\n")
    _commit_page(workspace, "two\n")
    service = _screen_service("page.tsx", app=App(roots=(".",), verified="VERIFIED", ignore=()))
    assert stale(service, str(workspace.api), str(workspace.artifacts)).stale == {}
    report = stale(service, str(workspace.api), str(workspace.artifacts), since=base)
    assert list(report.stale) == ["Dashboard"]
    assert report.verified == base


def test_stale_since_a_commit_is_judged_against_it_and_not_the_verified_commit(workspace):
    base = _commit_page(workspace, "one\n")
    head = _commit_page(workspace, "two\n")
    (workspace.artifacts / "VERIFIED").write_text(head)
    service = _screen_service("page.tsx", app=App(roots=(".",), verified="VERIFIED", ignore=()))
    assert stale(service, str(workspace.api), str(workspace.artifacts)).stale == {}
    assert list(stale(service, str(workspace.api), str(workspace.artifacts), since=base).stale) == ["Dashboard"]


def test_stale_since_names_a_new_file_no_element_names(workspace):
    base = _commit_page(workspace, "one\n")
    (workspace.api / "extra.tsx").write_text("x\n")
    _git(workspace.api, "add", "extra.tsx")
    _git(workspace.api, "commit", "--quiet", "-m", "extra")
    service = _screen_service("page.tsx", app=App(roots=(".",), verified="VERIFIED", ignore=()))
    report = stale(service, str(workspace.api), str(workspace.artifacts), since=base)
    assert list(report.unnamed) == ["extra.tsx"]


def _stale_command(workspace, monkeypatch, service, since):
    from ostler.book import cli
    monkeypatch.setattr(cli, "_package_dir", lambda args: str(workspace.artifacts))
    monkeypatch.setattr(cli, "load_decisions", lambda name: [])
    import argparse
    return cli.cmd_stale(service, argparse.Namespace(app=str(workspace.api), service="services.api", since=since))


def test_the_stale_command_with_since_reports_a_book_with_no_verified_commit_and_exits_1(workspace, monkeypatch, capsys):
    base = _commit_page(workspace, "one\n")
    _commit_page(workspace, "two\n")
    service = _screen_service("page.tsx", app=App(roots=(".",), verified="VERIFIED", ignore=()))
    assert _stale_command(workspace, monkeypatch, service, base) == 1
    out = capsys.readouterr().out
    assert f"since {base}" in out
    assert "- Dashboard: page.tsx" in out


def test_the_stale_command_with_since_exits_0_when_nothing_changed_after_it(workspace, monkeypatch, capsys):
    base = _commit_page(workspace, "one\n")
    service = _screen_service("page.tsx", app=App(roots=(".",), verified="VERIFIED", ignore=()))
    assert _stale_command(workspace, monkeypatch, service, base) == 0
    assert "nothing stale" in capsys.readouterr().out


def test_the_stale_command_without_since_still_exits_2_for_a_book_with_no_verified_commit(workspace, monkeypatch, capsys):
    _commit_page(workspace, "one\n")
    service = _screen_service("page.tsx", app=App(roots=(".",), verified="VERIFIED", ignore=()))
    assert _stale_command(workspace, monkeypatch, service, None) == 2


def test_the_stale_command_accepts_since():
    from ostler.book.cli import build_parser
    assert build_parser().parse_args(["stale", "services.api", "--app", "x", "--since", "abc"]).since == "abc"


def test_an_interaction_outside_the_screens_owes_no_source_pointer(workspace):
    outside = SimpleNamespace(__name__="ClockMoves", source=(), screen=None, carries=None)
    bound = SimpleNamespace(__name__="PressSave", source=(), screen=object(), carries=None)
    service = cast("Service[Any]", SimpleNamespace(endpoints=(), records=(), screens=(), interactions=(outside, bound), outside=(), app=None))
    found = source_faults(service, None)
    assert [(f.name, f.problem) for f in found] == [("PressSave", "no source pointer")]
