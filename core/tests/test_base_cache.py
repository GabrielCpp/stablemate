"""The shared base-library cache: a mirror of the base farrier ships, swapped in whole."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from stablemate_core import base_cache as bc


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Never touch the real ~/.cache/stablemate from a test."""
    monkeypatch.setenv(bc.CACHE_DIR_ENV, str(tmp_path / "cache"))


def _shipped(root: Path, skill: str = "demo") -> Path:
    """A base library as a farrier wheel holds it."""
    page = root / "library" / "skills" / skill / "SKILL.md"
    page.parent.mkdir(parents=True)
    page.write_text(f"# {skill}\n", encoding="utf-8")
    return root


def _cached_skills() -> list[str]:
    base = bc.cached_base()
    assert base is not None
    return sorted(p.name for p in (base / "library" / "skills").iterdir())


def test_mirrors_into_an_empty_cache(tmp_path, capsys):
    base = bc.mirror_base(_shipped(tmp_path / "shipped"), stamp="aaa")

    assert base == bc.cached_library_dir() / bc.BASE_SUBPATH
    assert _cached_skills() == ["demo"]
    assert bc.cached_stamp() == "aaa"
    assert "mirrored" in capsys.readouterr().out


def test_an_equal_stamp_copies_nothing(tmp_path, monkeypatch, capsys):
    shipped = _shipped(tmp_path / "shipped")
    bc.mirror_base(shipped, stamp="aaa")
    capsys.readouterr()
    monkeypatch.setattr(
        bc.shutil, "copytree", lambda *a, **k: pytest.fail("a current cache must not be copied over")
    )

    assert bc.mirror_base(shipped, stamp="aaa") == bc.cached_base()
    assert capsys.readouterr().out == ""


def test_a_new_stamp_replaces_the_whole_copy(tmp_path):
    """A skill the new farrier dropped must leave the cache too."""
    bc.mirror_base(_shipped(tmp_path / "old", "gone"), stamp="aaa")

    bc.mirror_base(_shipped(tmp_path / "new", "kept"), stamp="bbb")

    assert _cached_skills() == ["kept"]
    assert bc.cached_stamp() == "bbb"
    assert sorted(p.name for p in bc.cache_root().iterdir()) == ["library"]


def test_a_source_with_no_library_keeps_the_cache(tmp_path):
    bc.mirror_base(_shipped(tmp_path / "shipped"), stamp="aaa")

    assert bc.mirror_base(tmp_path / "broken", stamp="bbb") == bc.cached_base()
    assert bc.cached_stamp() == "aaa"


def test_a_failed_copy_keeps_the_cache_and_leaves_no_debris(tmp_path, monkeypatch):
    bc.mirror_base(_shipped(tmp_path / "shipped"), stamp="aaa")

    def disk_full(*a, **k):
        raise OSError("no space left on device")

    monkeypatch.setattr(bc.shutil, "copytree", disk_full)

    assert bc.mirror_base(_shipped(tmp_path / "next", "next"), stamp="bbb") == bc.cached_base()
    assert _cached_skills() == ["demo"]
    assert sorted(p.name for p in bc.cache_root().iterdir()) == ["library"]


def test_a_failed_swap_puts_the_old_cache_back(tmp_path, monkeypatch):
    bc.mirror_base(_shipped(tmp_path / "shipped"), stamp="aaa")
    real_rename = Path.rename

    def rename(self, target):
        if self.name.startswith(".library-mirror-"):
            raise OSError("cross-device link")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", rename)

    assert bc.mirror_base(_shipped(tmp_path / "next", "next"), stamp="bbb") is not None
    assert _cached_skills() == ["demo"]
    assert bc.cached_stamp() == "aaa"


def test_bytecode_is_not_mirrored(tmp_path):
    shipped = _shipped(tmp_path / "shipped")
    (shipped / "library" / "__pycache__").mkdir()
    (shipped / "library" / "__pycache__" / "x.pyc").write_bytes(b"\0")

    base = bc.mirror_base(shipped, stamp="aaa")

    assert base is not None
    assert not (base / "library" / "__pycache__").exists()


def test_cached_base_is_none_on_an_empty_cache():
    assert bc.cached_base() is None
    assert bc.cached_stamp() is None


def test_cache_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv(bc.CACHE_DIR_ENV, str(tmp_path / "elsewhere"))
    assert bc.cache_root() == tmp_path / "elsewhere"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
