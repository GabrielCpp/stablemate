"""Suite-wide guarantees: no network, no reading the developer's real config.

Two routes leak real state into a test here, and both must be closed:

* the base-library cache — resolving a base with nothing configured would clone ~16M
  from GitHub into the real ~/.cache/stablemate;
* the config file — pointing $STABLEMATE_CONFIG at a tmpdir is not enough, because
  when that file is absent read_config() falls back to the legacy per-tool paths
  (~/.config/workhorse, ~/.config/farrier), so a test would read whatever this
  machine has configured.
"""

from __future__ import annotations

import pytest

from stablemate_core import base_cache, config


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
