"""A surface's product source lives in the run's own repository, or in one member of the active workspace."""
from __future__ import annotations

from pathlib import Path

import pytest
from okf_book.support import MEMBER, Workspace
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.okf_book.shared.source_repo import SourceRepo, source_repo


def test_outside_a_workspace_the_source_is_the_run_s_own_repository(tmp_path: Path) -> None:
    repo = source_repo(tmp_path, "api", "")

    assert repo == SourceRepo(name="", path=tmp_path)
    assert repo.cite("api/main.py") == "api/main.py"


def test_under_a_workspace_the_source_is_the_named_member(workspace: Workspace) -> None:
    repo = source_repo(workspace.docs, "api", MEMBER)

    assert repo == SourceRepo(name=MEMBER, path=workspace.member)
    assert repo.cite("api/main.py") == f"repo://{MEMBER}/api/main.py"


def test_under_a_workspace_a_surface_without_a_repo_is_refused_with_the_member_names(workspace: Workspace) -> None:
    with pytest.raises(WorkflowFailed, match=rf"api.*{MEMBER}"):
        _ = source_repo(workspace.docs, "api", "")


def test_under_a_workspace_a_repo_that_is_no_member_is_refused_with_the_member_names(workspace: Workspace) -> None:
    with pytest.raises(WorkflowFailed, match=rf"api.*nowhere.*{MEMBER}"):
        _ = source_repo(workspace.docs, "api", "nowhere")


def test_outside_a_workspace_a_repo_is_refused(tmp_path: Path) -> None:
    with pytest.raises(WorkflowFailed, match="api.*no workspace"):
        _ = source_repo(tmp_path, "api", MEMBER)
