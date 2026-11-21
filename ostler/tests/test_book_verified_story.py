"""`ostler book stale --story` and `verified --story` judge only the commits whose trailer names the story, and write the stamp only when nothing else is left unnamed."""

from __future__ import annotations

from pathlib import Path

import pytest

from book_fakes import app_repo, book_command, commit_files, sourced_book
from ostler.book import change, cli, sources
from test_book_affected import FILES, edited

STORY = "feat: x\n\nStory: ACME-1"
OTHER = "feat: y\n\nStory: ACME-2"
BOOK: dict[str, tuple[str, ...]] = {"RemoveItem": ("remove.go::Remove",), "PutItem": ("svc.go::Server.Get",)}


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    return app_repo(tmp_path, FILES)


def stamp(tmp_path: Path, base: str) -> str:
    (tmp_path / "VERIFIED").write_text(base + "\n")
    return base


def command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys, where: Path, name: str, *flags: str) -> tuple[int, str]:
    return book_command(monkeypatch, tmp_path, sourced_book(BOOK), capsys, name, "services.shelf", "--app", str(where), *flags)


def test_verified_under_story_ignores_a_foreign_commits_unnamed_code_and_leaves_the_stamp(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    stamp(tmp_path, base)
    commit_files(where, edited("remove.go", "return id", "return id + id"), STORY)
    commit_files(where, edited("other.go", "return 1", "return 2"), OTHER)
    code, out = command(monkeypatch, tmp_path, capsys, where, "verified", "--story", "ACME-1")
    assert (code, out.startswith("not stamped")) == (0, True)
    assert (tmp_path / "VERIFIED").read_text().strip() == base
    code, out = command(monkeypatch, tmp_path, capsys, where, "verified")
    assert (code, out.startswith("not verified")) == (1, True)


def test_verified_under_story_refuses_the_storys_own_unnamed_code(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    stamp(tmp_path, base)
    commit_files(where, edited("other.go", "return 1", "return 2"), STORY)
    code, out = command(monkeypatch, tmp_path, capsys, where, "verified", "--story", "ACME-1")
    assert (code, out.startswith("not verified")) == (1, True)
    assert (tmp_path / "VERIFIED").read_text().strip() == base


def test_verified_under_story_stamps_head_when_every_change_is_named(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    stamp(tmp_path, base)
    commit_files(where, edited("remove.go", "return id", "return id + id"), STORY)
    head = commit_files(where, edited("svc.go", 'return "b"', 'return "z"'), OTHER)
    code, _ = command(monkeypatch, tmp_path, capsys, where, "verified", "--story", "ACME-1")
    assert code == 0
    assert (tmp_path / "VERIFIED").read_text().strip() == head


def test_verified_under_story_with_no_trailer_commit_exits_2(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    stamp(tmp_path, base)
    commit_files(where, edited("remove.go", "return id", "return id + id"), OTHER)
    code, out = command(monkeypatch, tmp_path, capsys, where, "verified", "--story", "ACME-1")
    assert code == 2
    assert "Story: ACME-1" in out
    assert (tmp_path / "VERIFIED").read_text().strip() == base


def test_stale_under_story_lists_only_the_storys_commits(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    stamp(tmp_path, base)
    commit_files(where, edited("remove.go", "return id", "return id + id"), STORY)
    commit_files(where, edited("other.go", "return 1", "return 2"), OTHER)
    monkeypatch.setattr(cli, "load_decisions", lambda name: [])
    code, out = command(monkeypatch, tmp_path, capsys, where, "stale", "--story", "ACME-1")
    assert code == 1
    assert out.splitlines()[0].startswith("story ACME-1: 1 commit(s) after")
    assert "other.go" not in out
    assert "- RemoveItem: remove.go::Remove" in out.split("## Stale elements")[1].split("##")[0]


def test_on_a_story_branch_the_story_reading_equals_the_range(tmp_path, repo):
    where, base = repo
    commit_files(where, edited("remove.go", "return id", "return id + id"), STORY)
    commit_files(where, edited("other.go", "return 1", "return 2"), STORY)
    commit_files(where, edited("svc.go", "return 1", "return 3"), STORY)
    book = sourced_book(BOOK)
    ranged = sources.stale(book, str(where), str(tmp_path), since=base)
    window = change.story_window(str(where), "ACME-1", base, (".",))
    assert window is not None
    read = sources.stale(book, str(where), str(tmp_path), window=window)
    assert (read.stale, read.unnamed, read.functions, read.beside, read.missing) == (ranged.stale, ranged.unnamed, ranged.functions, ranged.beside, ranged.missing)
    assert read.unnamed and read.functions


def test_the_stale_and_verified_parsers_accept_story():
    parser = cli.build_parser()
    assert parser.parse_args(["stale", "services.shelf", "--app", ".", "--story", "ACME-1"]).story == "ACME-1"
    assert parser.parse_args(["verified", "services.shelf", "--app", ".", "--story", "ACME-1"]).story == "ACME-1"
