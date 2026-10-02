"""A book is the files a writer put in it, never the state a tool keeps in a hidden folder beside them."""

from __future__ import annotations

from pathlib import Path

from ostler.pages import files_in_book, in_hidden_folder


def _touch(folder: Path, rel: str) -> Path:
    path = folder / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("x", encoding="utf-8")
    return path


def test_a_book_leaves_out_every_file_inside_a_hidden_folder(tmp_path: Path) -> None:
    for rel in ("index.md", "flows/sign-in.md", "flows/notes.txt", ".opencode/node_modules/uuid/README.md", "flows/.cache/stale.md"):
        _ = _touch(tmp_path, rel)

    assert files_in_book(tmp_path) == [tmp_path / "flows/sign-in.md", tmp_path / "index.md"]


def test_a_book_lists_each_suffix_it_is_asked_for(tmp_path: Path) -> None:
    for rel in ("a.md", "b.json", "c.txt", ".opencode/state.json"):
        _ = _touch(tmp_path, rel)

    assert files_in_book(tmp_path, (".md", ".json")) == [tmp_path / "a.md", tmp_path / "b.json"]


def test_only_a_hidden_folder_below_the_book_hides_a_file(tmp_path: Path) -> None:
    book = tmp_path / ".worktree" / "book"

    assert in_hidden_folder(book / ".opencode" / "x.md", book)
    assert not in_hidden_folder(book / "flows" / "x.md", book)
    assert not in_hidden_folder(book / ".hidden.md", book)
