"""Suite-wide guarantees: no network, no reading the developer's real config."""

from __future__ import annotations

import pytest

from farrier._vendor.stablemate_core import base_cache, config


@pytest.fixture(autouse=True)
def _no_base_fetch(tmp_path_factory, monkeypatch):
    monkeypatch.setenv(base_cache.FETCH_ENV, "0")
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
