"""Base-library resolution order — the single copy, shared by workhorse and farrier.

This lived twice, once per tool, testing two near-identical implementations. Both are
gone: discovery is core's, so its test is too. A base one tool can find and the other
cannot is indistinguishable from a broken library, which is why this cannot be
per-tool.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from stablemate_core import base_cache as bc
from stablemate_core import config as cfgmod
from stablemate_core.discovery import (
    BASE_DIR_ENV,
    base_library_dir,
    is_library_dir,
)


def _make_base(root: Path) -> Path:
    """A directory shaped like a usable library."""
    (root / "workflows").mkdir(parents=True)
    return root


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """A throwaway config the test can write keys into."""
    path = tmp_path / "config.toml"
    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(path))
    monkeypatch.delenv(BASE_DIR_ENV, raising=False)

    def set(**values):
        for k, v in values.items():
            cfgmod.write_config_key(k, v)

    return set


# --- the predicate -----------------------------------------------------------


def test_is_library_dir_accepts_either_content_dir(tmp_path):
    for name in ("library", "workflows"):
        root = tmp_path / name
        (root / name).mkdir(parents=True)
        assert is_library_dir(root)


def test_is_library_dir_rejects_an_empty_or_wrong_dir(tmp_path):
    assert not is_library_dir(tmp_path)
    (tmp_path / "packs").mkdir()
    assert not is_library_dir(tmp_path), "packs/ alone is not a library"


def test_is_library_dir_rejects_the_pre_flattening_layout(tmp_path):
    """base-library/ used to hold a Python package, not the payload.

    A cache fetched before the flattening looks exactly like this, and accepting it
    would hand callers a directory with no workflows in it.
    """
    (tmp_path / "stablemate_library" / "workflows").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("")
    assert not is_library_dir(tmp_path)


# --- resolution order --------------------------------------------------------


def test_checkout_derivation_is_the_lowest_real_source(tmp_path, cfg, monkeypatch):
    checkout = tmp_path / "checkout"
    derived = _make_base(checkout / "base-library")
    monkeypatch.setattr(bc, "cached_base", lambda: None)
    cfg(stablemate_dir=str(checkout))
    assert base_library_dir() == derived.resolve()


def test_config_base_dir_outranks_the_checkout(tmp_path, cfg, monkeypatch):
    checkout = tmp_path / "checkout"
    _make_base(checkout / "base-library")
    cfg_base = _make_base(tmp_path / "cfg")
    monkeypatch.setattr(bc, "cached_base", lambda: None)
    cfg(stablemate_dir=str(checkout), base_dir=str(cfg_base))
    assert base_library_dir() == cfg_base.resolve()


def test_env_var_outranks_everything(tmp_path, cfg, monkeypatch):
    cfg_base = _make_base(tmp_path / "cfg")
    env_base = _make_base(tmp_path / "env")
    monkeypatch.setattr(bc, "cached_base", lambda: None)
    cfg(base_dir=str(cfg_base))
    monkeypatch.setenv(BASE_DIR_ENV, str(env_base))
    assert base_library_dir() == env_base.resolve()


def test_cache_is_last_and_never_shadows_a_chosen_base(tmp_path, cfg, monkeypatch):
    """The whole reason the cache sits at the bottom: a download must not silently
    replace the checkout someone is editing."""
    cached = _make_base(tmp_path / "cached")
    checkout = tmp_path / "checkout"
    derived = _make_base(checkout / "base-library")
    monkeypatch.setattr(bc, "cached_base", lambda: cached)

    cfg(stablemate_dir=str(checkout))
    assert base_library_dir() == derived.resolve()


def test_cache_is_used_when_nothing_else_resolves(tmp_path, monkeypatch):
    cached = _make_base(tmp_path / "cached")
    monkeypatch.setattr(bc, "cached_base", lambda: cached)
    assert base_library_dir() == cached.resolve()


def test_nothing_configured_resolves_to_none(monkeypatch):
    monkeypatch.setattr(bc, "cached_base", lambda: None)
    assert base_library_dir() is None


# --- fail-soft ---------------------------------------------------------------


def test_invalid_override_is_skipped_not_raised(tmp_path, cfg, monkeypatch):
    """The base is additive: a bad override must leave an overlay-only setup working."""
    real = _make_base(tmp_path / "real")
    monkeypatch.setattr(bc, "cached_base", lambda: None)
    cfg(base_dir=str(tmp_path / "does-not-exist"), stablemate_dir=str(tmp_path / "nope"))
    monkeypatch.setenv(BASE_DIR_ENV, str(tmp_path / "also-not-there"))
    assert base_library_dir() is None

    monkeypatch.setenv(BASE_DIR_ENV, str(real))
    assert base_library_dir() == real.resolve()


def test_resolution_never_fetches(tmp_path, monkeypatch):
    monkeypatch.setattr(
        bc, "_clone_into", lambda dest: pytest.fail("resolution must never fetch")
    )
    base_library_dir()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
