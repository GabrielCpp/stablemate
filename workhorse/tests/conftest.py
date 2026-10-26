"""Suite-wide guarantees."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from workhorse._vendor.stablemate_core import base_cache, config


@pytest.fixture(autouse=True)
def _no_base_fetch(tmp_path_factory, monkeypatch):
    monkeypatch.setenv(base_cache.FETCH_ENV, "0")
    monkeypatch.setenv(
        base_cache.CACHE_DIR_ENV, str(tmp_path_factory.mktemp("stablemate-cache"))
    )


@pytest.fixture(autouse=True)
def _no_real_config(tmp_path_factory, monkeypatch):
    """Never read the developer's actual config."""
    monkeypatch.setenv(
        config.CONFIG_PATH_ENV,
        str(tmp_path_factory.mktemp("stablemate-config") / "config.toml"),
    )
    monkeypatch.delenv(config.LEGACY_CONFIG_PATH_ENV, raising=False)
    monkeypatch.setattr(config, "legacy_config_paths", list)


TOOL_CACHE = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")


@pytest.fixture(autouse=True)
def _no_real_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", TOOL_CACHE)
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    for name in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(name, raising=False)
