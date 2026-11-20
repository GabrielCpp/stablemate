"""Base-library resolution order — the single copy, shared by workhorse and farrier."""

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
    share_base_library,
)


def _make_base(root: Path) -> Path:
    """A directory shaped like a usable library."""
    (root / "library").mkdir(parents=True)
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




def test_is_library_dir_accepts_the_content_dir(tmp_path):
    (tmp_path / "library").mkdir()
    assert is_library_dir(tmp_path)


def test_is_library_dir_rejects_an_empty_or_wrong_dir(tmp_path):
    assert not is_library_dir(tmp_path)
    (tmp_path / "packs").mkdir()
    assert not is_library_dir(tmp_path), "packs/ alone is not a library"


def test_is_library_dir_rejects_a_workflows_only_dir(tmp_path):
    """`workflows/` used to be an accepted alternative to `library/`."""
    (tmp_path / "workflows").mkdir()
    assert not is_library_dir(tmp_path)


def test_is_library_dir_rejects_the_pre_flattening_layout(tmp_path):
    """base-library/ used to hold a Python package, not the payload."""
    (tmp_path / "stablemate_library" / "library").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("")
    assert not is_library_dir(tmp_path)




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
    """The whole reason the cache sits at the bottom: a download must not silently replace the checkout someone is editing."""
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




def test_invalid_override_is_skipped_not_raised(tmp_path, cfg, monkeypatch):
    """The base is additive: a bad override must leave an overlay-only setup working."""
    real = _make_base(tmp_path / "real")
    monkeypatch.setattr(bc, "cached_base", lambda: None)
    cfg(base_dir=str(tmp_path / "does-not-exist"), stablemate_dir=str(tmp_path / "nope"))
    monkeypatch.setenv(BASE_DIR_ENV, str(tmp_path / "also-not-there"))
    assert base_library_dir() is None

    monkeypatch.setenv(BASE_DIR_ENV, str(real))
    assert base_library_dir() == real.resolve()


def test_a_shipped_base_outranks_the_cache(tmp_path, monkeypatch):
    """The base a tool carries matches its own code; a mirror another farrier left may not."""
    shipped = _make_base(tmp_path / "shipped")
    monkeypatch.setattr(bc, "cached_base", lambda: _make_base(tmp_path / "cached"))
    assert base_library_dir(shipped) == shipped.resolve()


def test_a_named_base_outranks_the_shipped_one(tmp_path, cfg, monkeypatch):
    checkout = tmp_path / "checkout"
    derived = _make_base(checkout / "base-library")
    cfg(stablemate_dir=str(checkout))
    assert base_library_dir(_make_base(tmp_path / "shipped")) == derived.resolve()


def test_a_broken_shipped_base_falls_to_the_cache(tmp_path, monkeypatch):
    cached = _make_base(tmp_path / "cached")
    monkeypatch.setattr(bc, "cached_base", lambda: cached)
    assert base_library_dir(tmp_path / "not-there") == cached.resolve()




def test_share_mirrors_the_shipped_base(tmp_path, monkeypatch):
    monkeypatch.delenv(BASE_DIR_ENV, raising=False)
    shipped = _make_base(tmp_path / "shipped")

    cached = share_base_library(shipped, stamp="aaa", quiet=True)

    assert cached is not None
    assert cached == bc.cached_base()
    assert bc.cached_stamp() == "aaa"
    assert base_library_dir() == cached.resolve()


def test_share_writes_nothing_over_a_named_base(tmp_path, cfg, monkeypatch):
    """Someone editing a base in place must never have a copy appear underneath them."""
    checkout = tmp_path / "checkout"
    _make_base(checkout / "base-library")
    cfg(stablemate_dir=str(checkout))
    monkeypatch.setattr(
        bc, "mirror_base", lambda *a, **k: pytest.fail("a named base must not be mirrored over")
    )

    assert share_base_library(_make_base(tmp_path / "shipped"), stamp="aaa") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
