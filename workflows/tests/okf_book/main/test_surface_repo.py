"""A surface names the workspace member that holds its source, and a run refuses one that names the wrong place before any turn."""
from __future__ import annotations

from pathlib import Path

import pytest
from okf_book.main.tally import TALLY
from okf_book.support import MEMBER, MEMBER_FOLDER, Workspace
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.workflow import OkfBook


def _surface(repo: str) -> Surface:
    return Surface(service="ledger", kind=SurfaceKind.HTTP, entry=MEMBER_FOLDER, repo=repo)


def test_a_surface_names_no_repo_by_default() -> None:
    assert TALLY.repo == ""


def test_a_workspace_run_starts_when_each_surface_names_a_member(workspace: Workspace) -> None:
    book = OkfBook(repo_dir=str(workspace.member), parent_records_dir=str(workspace.docs), surfaces=(_surface(MEMBER),))

    assert book.start().state == "route_book"


def test_a_workspace_run_with_a_surface_that_names_no_repo_fails_before_any_turn(workspace: Workspace) -> None:
    book = OkfBook(repo_dir=str(workspace.member), parent_records_dir=str(workspace.docs), surfaces=(_surface(""),))

    with pytest.raises(WorkflowFailed, match=rf"ledger.*{MEMBER}"):
        _ = book.start()


def test_a_run_outside_a_workspace_with_a_surface_that_names_a_repo_fails_before_any_turn(tmp_path: Path) -> None:
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(_surface(MEMBER),))

    with pytest.raises(WorkflowFailed, match="ledger.*no workspace"):
        _ = book.start()
