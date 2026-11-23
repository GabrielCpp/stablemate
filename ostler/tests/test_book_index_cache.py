"""`ostler book search` keeps its index of a book in the user cache, keyed by the book folder's path, and writes nothing into the book."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import write
from ostler.book import cli
from ostler.book import index as book_index

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "xdg"
    monkeypatch.delenv("STABLEMATE_CACHE_DIR", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(folder))
    return folder


HERE: dict[str, Path] = {}


@pytest.fixture
def loads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def load(name: str) -> str:
        seen.append(name)
        return name

    def build(service: str, name: str) -> str:
        return f"endpoint\tThing\tendpoints.py:1\t{(HERE[name] / 'notes.md').read_text().strip()}\n"

    monkeypatch.setattr(cli, "load", load)
    monkeypatch.setattr(book_index, "build", build)
    return seen


def _book(root: Path, name: str, words: str) -> Path:
    folder = root / Path(*name.split("."))
    write(folder / "service.py", "")
    write(folder / "notes.md", words)
    return folder


def _words(root: Path, name: str) -> list[str]:
    HERE[name] = root / Path(*name.split("."))
    return [line for entry in book_index.entries_of(str(root), name) for line in entry.lines]


def test_a_first_search_builds_and_writes_the_cache_and_a_second_reads_it(tmp_path, cache, loads):
    root = tmp_path / "book"
    folder = _book(root, "services.demo", "ambrosia\n")
    assert _words(root, "services.demo") == ["ambrosia"]
    assert Path(book_index.cache_path(str(folder))).is_file()
    assert Path(book_index.cache_path(str(folder))).is_relative_to(cache / "stablemate" / "book-index")
    assert not (folder / "index.tsv").exists()
    assert loads == ["services.demo"]
    assert _words(root, "services.demo") == ["ambrosia"]
    assert loads == ["services.demo"]


def test_a_change_to_the_book_makes_the_cache_stale(tmp_path, cache, loads):
    root = tmp_path / "book"
    folder = _book(root, "services.demo", "ambrosia\n")
    assert _words(root, "services.demo") == ["ambrosia"]
    notes = folder / "notes.md"
    notes.write_text("nectar\n")
    later = time.time() + 10
    os.utime(notes, (later, later))
    assert _words(root, "services.demo") == ["nectar"]
    assert len(loads) == 2


def test_an_unwritable_cache_folder_still_returns_results(tmp_path, monkeypatch, loads):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the cache folder would go")
    monkeypatch.delenv("STABLEMATE_CACHE_DIR", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(blocker))
    root = tmp_path / "book"
    _book(root, "services.demo", "ambrosia\n")
    assert _words(root, "services.demo") == ["ambrosia"]


def test_two_book_folders_with_one_module_name_get_two_cache_files(tmp_path, cache, loads):
    first = _book(tmp_path / "book", "services.demo", "ambrosia\n")
    second = _book(tmp_path / "other", "services.demo", "nectar\n")
    assert book_index.cache_path(str(first)) != book_index.cache_path(str(second))
    assert _words(tmp_path / "book", "services.demo") == ["ambrosia"]
    assert _words(tmp_path / "other", "services.demo") == ["nectar"]
    assert len(list(Path(book_index.cache_path(str(first))).parent.glob("*.tsv"))) == 2


def test_check_with_no_cache_reports_no_index_finding_and_writes_the_cache(tmp_path):
    env = dict(os.environ)
    env["XDG_CACHE_HOME"] = str(tmp_path / "xdg")
    env.pop("STABLEMATE_CACHE_DIR", None)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    done = subprocess.run([sys.executable, "-m", "ostler.book", "check", "services.farrier"], cwd=ROOT, env=env,
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.strip().endswith("check: 0 findings")
    assert list((tmp_path / "xdg" / "stablemate" / "book-index").glob("*.tsv"))
    assert not (ROOT / "services" / "farrier" / "index.tsv").exists()
