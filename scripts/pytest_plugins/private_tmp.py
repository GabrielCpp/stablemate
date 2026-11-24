"""Pytest plugin: the run owns a private temp folder and removes it when it passes."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

PREFIX = "sm-t-"
MAX_AGE_SECONDS = 24 * 60 * 60

_state: dict[str, object] = {}


def _sweep_stale() -> None:
    cutoff = time.time() - MAX_AGE_SECONDS
    for entry in Path(tempfile.gettempdir()).glob(f"{PREFIX}*"):
        try:
            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
        except OSError:
            continue


def _restore() -> None:
    previous = _state.get("previous")
    if previous is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = str(previous)
    tempfile.tempdir = None


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    if hasattr(config, "workerinput") or "folder" in _state:
        return
    tempfile.tempdir = None
    _sweep_stale()
    _state["previous"] = os.environ.get("TMPDIR")
    folder = tempfile.mkdtemp(prefix=PREFIX)
    _state["folder"] = folder
    os.environ["TMPDIR"] = folder
    tempfile.tempdir = None
    if config.option.basetemp is None:
        config.option.basetemp = Path(folder) / "b"


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if hasattr(session.config, "workerinput"):
        return
    folder = _state.get("folder")
    if folder is None:
        return
    if exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
        shutil.rmtree(str(folder), ignore_errors=True)
        _state.pop("kept", None)
    else:
        _state["kept"] = folder
    _state.pop("folder")
    _restore()


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    kept = _state.pop("kept", None)
    if kept is not None:
        terminalreporter.write_line(f"private temp folder kept: {kept}")
