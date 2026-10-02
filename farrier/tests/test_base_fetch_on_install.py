"""`farrier install` checks out the base library, and updates it."""
from __future__ import annotations

import importlib.metadata
from pathlib import Path
from types import SimpleNamespace

import pytest

from farrier import layers as _layers
from farrier._vendor.stablemate_core import discovery
from farrier.install import main

RELEASE_TAG = "farrier-v9.9.9"
CHECKOUT_RECORD = '{"url": "file:///src/farrier", "dir_info": {"editable": true}}'


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
    """A repo selecting a skill the library layer has to supply — so a run that resolved no base would fail rather than pass vacuously."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "agents.yml").write_text(
        'agents: [claude]\nskills: ["demo/*"]\n', encoding="utf-8"
    )
    return root


@pytest.fixture
def base(tmp_path: Path) -> Path:
    return _library(tmp_path / "base")


def _installed_as(monkeypatch, direct_url: str | None) -> None:
    """Stand in for farrier's install record: a PyPI install writes no `direct_url.json`, a checkout or a URL does."""
    real = importlib.metadata.distribution
    fake = SimpleNamespace(version="9.9.9", read_text=lambda name: direct_url)
    monkeypatch.setattr(
        importlib.metadata,
        "distribution",
        lambda name: fake if name == "farrier" else real(name),
    )


@pytest.fixture
def spy(monkeypatch, base):
    """Record which cache call install made, without going near the network."""
    monkeypatch.delenv(discovery.BASE_DIR_ENV, raising=False)
    calls: list[tuple[str, str]] = []

    def fetch(*, ref, quiet=False):
        calls.append(("fetch", ref))
        return base

    def refresh(*, ref, quiet=False):
        calls.append(("refresh", ref))
        return base

    monkeypatch.setattr(discovery.base_cache, "ensure_cached_base", fetch)
    monkeypatch.setattr(discovery.base_cache, "refresh_cached_base", refresh)
    monkeypatch.setattr(discovery.base_cache, "cached_base", lambda: base)
    _installed_as(monkeypatch, None)
    return calls


def test_install_refreshes_the_base_to_its_own_release_tag(repo, spy):
    """A released farrier renders the library it shipped with, not whatever main holds today."""
    main(["install", "--repo", str(repo)])
    assert spy == [("refresh", RELEASE_TAG)]


def test_an_unreleased_farrier_tracks_main(repo, spy, monkeypatch):
    """A checkout or a git install runs code no tag holds, so its library is main's too."""
    _installed_as(monkeypatch, CHECKOUT_RECORD)
    main(["install", "--repo", str(repo)])
    assert spy == [("refresh", "main")]


def test_check_fetches_but_does_not_refresh(repo, spy):
    main(["install", "--repo", str(repo), "--check"])
    assert spy == [("fetch", RELEASE_TAG)]


def test_the_default_action_refreshes_too(repo, spy):
    """`farrier --repo .` is the documented spelling; `install` is the alias."""
    main(["--repo", str(repo)])
    assert spy == [("refresh", RELEASE_TAG)]


def test_the_fetched_base_becomes_a_layer(repo, spy, base):
    main(["install", "--repo", str(repo)])
    assert base.resolve() in [layer.root for layer in _layers.LAYERS]


def test_a_configured_base_is_not_fetched_over(repo, base, monkeypatch):
    """End to end through the real discovery function rather than the spy: the ordering guarantee is only worth anything if install goes through it."""
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
    """Fail-soft: no network and no base must still render an overlay-only setup, exactly as it did before install fetched anything."""
    overlay = _library(tmp_path / "overlay")
    monkeypatch.setattr("farrier.cli.ensure_base_library_dir", lambda **k: None)

    assert main(["install", "--repo", str(repo), "--library", str(overlay)]) == 0
    assert [layer.root for layer in _layers.LAYERS] == [overlay.resolve()]


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
