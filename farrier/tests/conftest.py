"""Suite-wide guarantees: no shipped base, no real cache, no reading the developer's real config."""

from __future__ import annotations

from pathlib import Path

import pytest

from farrier import layers
from farrier._vendor.stablemate_core import base_cache, config
from home_install import agent_library, isolated_home

pytest_plugins = ["private_tmp"]


@pytest.fixture(autouse=True)
def _no_shipped_base(tmp_path_factory, monkeypatch):
    monkeypatch.setattr(
        layers,
        "SHIPPED_BASE",
        tmp_path_factory.mktemp("no-shipped-base") / "base_library",
    )
    monkeypatch.setenv(
        base_cache.CACHE_DIR_ENV, str(tmp_path_factory.mktemp("stablemate-cache"))
    )


@pytest.fixture(autouse=True)
def _no_real_config(tmp_path_factory, monkeypatch):
    monkeypatch.setenv(
        config.CONFIG_PATH_ENV,
        str(tmp_path_factory.mktemp("stablemate-config") / "config.toml"),
    )
    monkeypatch.setattr(config, "legacy_config_paths", list)


@pytest.fixture
def library(tmp_path: Path) -> Path:
    return agent_library(tmp_path)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return isolated_home(tmp_path, monkeypatch)
