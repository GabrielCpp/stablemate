"""`farrier install` checks out the base library, and updates it.

The cache route existed for a long time with nothing populating it: `base_cache`
implemented the whole fetch and no command called it, so in practice a working setup
came from `$STABLEMATE_BASE_DIR`, `config set-base` or a `stablemate_dir` checkout.
Install is the command that now closes that gap, and these pin the three decisions that
came with it:

* install *refreshes*, where every other caller freezes — it is an operator asking for a
  re-render at a moment they chose, not a background timer;
* `--check` fetches but does not refresh, because it runs in CI and a library moving
  underneath the comparison turns a drift report into a coin-flip;
* a base someone named on disk is still never fetched over.

    ./.venv/bin/python -m pytest tests/test_base_fetch_on_install.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

from farrier import layers as _layers
from farrier._vendor.stablemate_core import discovery
from farrier.install import main


def _library(root: Path) -> Path:
    """A directory shaped like a usable library, holding the one skill the repo selects."""
    skill = root / "library" / "skills" / "demo" / "thing" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        '---\nname: thing\ndescription: "a skill"\n---\n\n# Thing\n', encoding="utf-8"
    )
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo selecting a skill the library layer has to supply — so a run that resolved
    no base would fail rather than pass vacuously."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "agents.yml").write_text(
        'agents: [claude]\nskills: ["demo/*"]\n', encoding="utf-8"
    )
    return root


@pytest.fixture
def base(tmp_path: Path) -> Path:
    return _library(tmp_path / "base")


@pytest.fixture
def spy(monkeypatch, base):
    """Record which cache call install made, without going near the network.

    Patched at the `base_cache` seam rather than over `ensure_base_library_dir`, so the
    real resolution order still runs — install resolves the base twice (once to populate
    it, once when `set_layers` looks it up), and a stub that skipped discovery would hide
    the two disagreeing.
    """
    monkeypatch.delenv(discovery.BASE_DIR_ENV, raising=False)
    calls: list[str] = []

    def fetch(*, quiet=False):
        calls.append("fetch")
        return base

    def refresh(*, quiet=False):
        calls.append("refresh")
        return base

    monkeypatch.setattr(discovery.base_cache, "ensure_cached_base", fetch)
    monkeypatch.setattr(discovery.base_cache, "refresh_cached_base", refresh)
    # The lookup half of the order, standing in for "the fetch left this on disk".
    monkeypatch.setattr(discovery.base_cache, "cached_base", lambda: base)
    return calls


def test_install_refreshes_the_base(repo, spy):
    main(["install", "--repo", str(repo)])
    assert spy == ["refresh"]


def test_check_fetches_but_does_not_refresh(repo, spy):
    main(["install", "--repo", str(repo), "--check"])
    assert spy == ["fetch"]


def test_the_default_action_refreshes_too(repo, spy):
    """`farrier --repo .` is the documented spelling; `install` is the alias. They must
    not differ on whether the library gets updated."""
    main(["--repo", str(repo)])
    assert spy == ["refresh"]


def test_the_fetched_base_becomes_a_layer(repo, spy, base):
    main(["install", "--repo", str(repo)])
    assert base.resolve() in [layer.root for layer in _layers.LAYERS]


def test_a_configured_base_is_not_fetched_over(repo, base, monkeypatch):
    """End to end through the real discovery function rather than the spy: the ordering
    guarantee is only worth anything if install goes through it."""
    monkeypatch.setenv(discovery.BASE_DIR_ENV, str(base))
    monkeypatch.setattr(
        discovery.base_cache,
        "refresh_cached_base",
        lambda **k: pytest.fail("a chosen base must not be refetched"),
    )

    main(["install", "--repo", str(repo)])

    assert base.resolve() in [layer.root for layer in _layers.LAYERS]


def test_install_survives_a_failed_fetch_when_an_overlay_exists(
    repo, tmp_path, monkeypatch
):
    """Fail-soft: no network and no base must still render an overlay-only setup, exactly
    as it did before install fetched anything."""
    overlay = _library(tmp_path / "overlay")
    monkeypatch.setattr("farrier.cli.ensure_base_library_dir", lambda **k: None)

    assert main(["install", "--repo", str(repo), "--library", str(overlay)]) == 0
    assert [layer.root for layer in _layers.LAYERS] == [overlay.resolve()]


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
