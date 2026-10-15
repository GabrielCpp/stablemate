"""Suite-wide isolation that no single test file can give itself."""
from __future__ import annotations

import os
from pathlib import Path

import logging
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _logging_handlers_do_not_outlive_the_test() -> Iterator[None]:
    """Put every logger's handlers back the way the test found them."""
    loggers = [logging.getLogger(), *(
        logger for logger in logging.Logger.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    )]
    saved = {logger: list(logger.handlers) for logger in loggers}
    yield
    for logger in [logging.getLogger(), *logging.Logger.manager.loggerDict.values()]:
        if isinstance(logger, logging.Logger):
            logger.handlers[:] = saved.get(logger, [])


TOOL_CACHE = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")


@pytest.fixture(autouse=True)
def _no_real_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", TOOL_CACHE)
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path_factory.mktemp("stablemate-cache")))
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))


class _RefusingSupervisor:
    def spawn(self, *args, **kwargs):
        raise RuntimeError("groom tests never spawn a real process")


@pytest.fixture(autouse=True, scope="session")
def _no_real_spawn() -> Iterator[None]:
    from groom import attend, dispatch

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(dispatch, "ProcessSupervisor", _RefusingSupervisor)
        patch.setattr(attend, "ProcessSupervisor", _RefusingSupervisor)
        yield
