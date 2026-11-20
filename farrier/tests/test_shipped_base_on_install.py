"""`farrier install` renders the base library it ships, and mirrors it for the other tools."""
from __future__ import annotations

from pathlib import Path

import pytest

from farrier import layers as _layers
from farrier._vendor.stablemate_core import base_cache, discovery
from farrier.install import main

REAL_SHIPPED_BASE = _layers.SHIPPED_BASE


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
def shipped(tmp_path: Path, monkeypatch) -> Path:
    """A farrier whose wheel holds a base library and its digest."""
    monkeypatch.delenv(discovery.BASE_DIR_ENV, raising=False)
    base = _library(tmp_path / "wheel" / "_vendor" / "base_library")
    base.with_name("base_library.sha256").write_text("aaa\n", encoding="utf-8")
    monkeypatch.setattr(_layers, "SHIPPED_BASE", base)
    return base


def test_install_renders_the_shipped_base(repo, shipped):
    assert main(["install", "--repo", str(repo)]) == 0
    assert list((repo / ".claude" / "skills").glob("*thing/SKILL.md"))
    assert [layer.root for layer in _layers.LAYERS] == [shipped.resolve()]


def test_install_mirrors_the_shipped_base_with_its_digest(repo, shipped):
    main(["install", "--repo", str(repo)])

    cached = base_cache.cached_base()
    assert cached is not None
    assert (cached / "library" / "skills" / "demo" / "thing" / "SKILL.md").is_file()
    assert base_cache.cached_stamp() == "aaa"


def test_the_default_action_mirrors_too(repo, shipped):
    """`farrier --repo .` is the documented spelling; `install` is the alias."""
    main(["--repo", str(repo)])
    assert base_cache.cached_stamp() == "aaa"


def test_check_writes_no_cache(repo, shipped):
    main(["install", "--repo", str(repo), "--check"])
    assert base_cache.cached_base() is None


def test_a_named_base_is_not_mirrored_over(repo, shipped, tmp_path, monkeypatch):
    """End to end through the real discovery function: the ordering guarantee is only worth anything if install goes through it."""
    named = _library(tmp_path / "named")
    monkeypatch.setenv(discovery.BASE_DIR_ENV, str(named))

    main(["install", "--repo", str(repo)])

    assert [layer.root for layer in _layers.LAYERS] == [named.resolve()]
    assert base_cache.cached_base() is None


def test_the_real_wheel_ships_a_base_and_its_digest():
    """The link and the stamp `make vendor` writes are what the wheel builder follows."""
    assert discovery.is_library_dir(REAL_SHIPPED_BASE)
    assert REAL_SHIPPED_BASE.with_name("base_library.sha256").read_text(encoding="utf-8").strip()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
