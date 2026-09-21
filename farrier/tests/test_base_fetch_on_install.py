"""`farrier install` checks out the base library, and updates it."""
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


@pytest.fixture
def spy(monkeypatch, base):
    """Record which cache call install made, without going near the network."""
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
    monkeypatch.setattr(discovery.base_cache, "cached_base", lambda: base)
    return calls


def test_install_refreshes_the_base(repo, spy):
    main(["install", "--repo", str(repo)])
    assert spy == ["refresh"]


def test_check_fetches_but_does_not_refresh(repo, spy):
    main(["install", "--repo", str(repo), "--check"])
    assert spy == ["fetch"]


def test_the_default_action_refreshes_too(repo, spy):
    """`farrier --repo .` is the documented spelling; `install` is the alias."""
    main(["--repo", str(repo)])
    assert spy == ["refresh"]


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
