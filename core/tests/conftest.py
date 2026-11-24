"""Suite-wide guarantees: no network, no reading the developer's real config."""

from __future__ import annotations

import pytest

from stablemate_core import base_cache, config

pytest_plugins = ["private_tmp"]


@pytest.fixture(autouse=True)
def _no_real_cache(tmp_path_factory, monkeypatch):
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


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setenv(config.CONFIG_PATH_ENV, str(path))
    return path
