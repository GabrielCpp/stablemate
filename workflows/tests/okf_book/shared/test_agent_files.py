"""A book commit renders the repo's agent files first, and says why when the render could not run."""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from workhorse_workflows.okf_book.shared import agent_files
from workhorse_workflows.okf_book.shared.agent_files import AGENTS_CONFIG, render_agent_files_returning_failure


def _farrier_exits(code: int, calls: list[list[str]]) -> Callable[[list[str], object], subprocess.CompletedProcess[str]]:
    def _run(argv: list[str], _cwd: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, code, stdout="", stderr="no library")

    return _run


def test_a_repo_that_selects_no_agent_files_is_not_rendered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(agent_files, "run_tool", _farrier_exits(0, calls))

    assert render_agent_files_returning_failure(tmp_path) == ""
    assert calls == []


def test_a_repo_with_an_agents_config_is_rendered_by_farrier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = (tmp_path / AGENTS_CONFIG).write_text("assistants: []\n", encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setattr(agent_files, "run_tool", _farrier_exits(0, calls))

    assert render_agent_files_returning_failure(tmp_path) == ""
    assert calls == [["farrier", "install", "--repo", str(tmp_path)]]


def test_a_render_farrier_refuses_says_what_farrier_said(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = (tmp_path / AGENTS_CONFIG).write_text("assistants: []\n", encoding="utf-8")
    monkeypatch.setattr(agent_files, "run_tool", _farrier_exits(1, []))

    assert render_agent_files_returning_failure(tmp_path) == "farrier could not render them: no library"


def test_a_machine_without_farrier_says_farrier_could_not_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = (tmp_path / AGENTS_CONFIG).write_text("assistants: []\n", encoding="utf-8")

    def _missing(argv: list[str], _cwd: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(agent_files, "run_tool", _missing)

    assert render_agent_files_returning_failure(tmp_path).startswith("farrier could not run:")
