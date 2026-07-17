"""Suite-wide guarantees: no network, no reading the developer's real config.

Both are live hazards here rather than theoretical ones. Resolving a base with nothing
configured clones ~16M from GitHub into the real ~/.cache/stablemate — correct in
production, intolerable in a unit test. And redirecting $STABLEMATE_CONFIG at a tmpdir
is not enough on its own: when that file is absent the legacy per-tool paths are read,
so a test would pick up whatever this machine has configured.
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
