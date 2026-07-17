"""Suite-wide guarantees.

Tests here are dependency-free and standalone by contract: nothing hits the network
and nothing waits in real time. The base-library cache is a standing threat to the
first half of that — resolving a bare workflow name with no library configured will
clone ~16M from GitHub into the developer's real ~/.cache/stablemate, which is correct
in production and intolerable in a unit test.

So the fetch is off for every test by default, and the cache is redirected into a
tmpdir. A test that wants to exercise fetching (tests/test_base_cache.py) opts back in
by patching the clone seam, which never reaches the network either.
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
    """Never read the developer's actual config.

    Pointing $STABLEMATE_CONFIG at a tmpdir is not enough on its own: when that file
    is absent, load_config() falls back to the legacy per-tool paths — the real
    ~/.config/workhorse and ~/.config/farrier. A test would then read whatever
    library_dir this machine happens to have set. Neutralize both routes; tests that
    exercise legacy fallback re-patch it themselves.
    """
    monkeypatch.setenv(
        config.CONFIG_PATH_ENV,
        str(tmp_path_factory.mktemp("stablemate-config") / "config.toml"),
    )
    monkeypatch.delenv(config.LEGACY_CONFIG_PATH_ENV, raising=False)
    monkeypatch.setattr(config, "legacy_config_paths", list)
