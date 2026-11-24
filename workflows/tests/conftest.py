"""Suite-wide fixtures for the workflows tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest_plugins = ["private_tmp"]


@pytest.fixture(autouse=True)
def _artifacts_dir_is_per_test(tmp_path_factory, monkeypatch):
    """Specs live in the user's artifacts folder, so no test may resolve to the real one."""
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(tmp_path_factory.mktemp("artifacts")))


TOOL_CACHE = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")


@pytest.fixture(autouse=True)
def _no_real_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", TOOL_CACHE)
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path_factory.mktemp("stablemate-cache")))
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
