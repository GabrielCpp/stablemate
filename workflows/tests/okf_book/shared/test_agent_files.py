"""A book commit renders the repo's agent files first, and a render that cannot run leaves the commit to the hook."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from workhorse_workflows.okf_book.shared import agent_files
from workhorse_workflows.okf_book.shared.agent_files import AGENTS_CONFIG, render_agent_files

LOGGER = logging.getLogger("test_agent_files")


def _farrier_exits(code: int, calls: list[list[str]]) -> object:
    def _run(argv: list[str], _cwd: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, code, stdout="", stderr="no library")

    return _run


def test_a_repo_that_selects_no_agent_files_is_not_rendered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(agent_files, "run_tool", _farrier_exits(0, calls))

    render_agent_files(tmp_path, LOGGER)

    assert calls == []


def test_a_repo_with_an_agents_config_is_rendered_by_farrier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = (tmp_path / AGENTS_CONFIG).write_text("assistants: []\n", encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setattr(agent_files, "run_tool", _farrier_exits(0, calls))

    render_agent_files(tmp_path, LOGGER)

    assert calls == [["farrier", "install", "--repo", str(tmp_path)]]


def test_a_render_farrier_refuses_is_logged_and_left_to_the_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _ = (tmp_path / AGENTS_CONFIG).write_text("assistants: []\n", encoding="utf-8")
    monkeypatch.setattr(agent_files, "run_tool", _farrier_exits(1, []))

    with caplog.at_level(logging.WARNING):
        render_agent_files(tmp_path, LOGGER)

    assert "no library" in caplog.text


def test_a_machine_without_farrier_is_logged_and_left_to_the_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _ = (tmp_path / AGENTS_CONFIG).write_text("assistants: []\n", encoding="utf-8")

    def _missing(argv: list[str], _cwd: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(agent_files, "run_tool", _missing)

    with caplog.at_level(logging.WARNING):
        render_agent_files(tmp_path, LOGGER)

    assert "farrier could not run" in caplog.text
