"""The catalog model and the book-root repository declaration.

Building a catalog (`build_catalog`, once here) is retired: `ostler stamp` grounds a
citation with a digest carried on the bullet itself, scoped to exactly the file that
bullet cites, rather than a whole-book snapshot rewritten on every repair. What survives
is the catalog *shape* — `SourceCatalog`/`RepositorySnapshot`/`SourceFile`/`SourceSymbol`
— because `load_catalog` still reads a catalog written before the retirement, backing
`ostler stamp --from-catalog --keep-catalog`'s one-time migration off it.
"""
from __future__ import annotations

from pathlib import Path

from ostler import source_snapshots

# --- the book-root repository declaration -----------------------------------------


def test_book_repository_is_empty_when_undeclared(tmp_path: Path) -> None:
    """A book with no declaration reads as empty, not as a default guess.

    Multi-repo workspaces without a declaration are reported by doctor rather than silently
    joining a node to the wrong history.
    """
    book = tmp_path / "docs/features/api"
    book.mkdir(parents=True)
    assert source_snapshots.book_repository(book) == ""


def test_set_book_repository_round_trips(tmp_path: Path) -> None:
    book = tmp_path / "docs/features/api"
    book.mkdir(parents=True)

    written = source_snapshots.set_book_repository(book, "api-service")
    assert source_snapshots.book_repository(book) == "api-service"
    assert written.read_text(encoding="utf-8").strip() == "api-service"


def test_book_repository_strips_surrounding_whitespace(tmp_path: Path) -> None:
    """A trailing newline or surrounding whitespace is the writer's politeness, not the data."""
    book = tmp_path / "docs/features/api"
    book.mkdir(parents=True)
    (book / source_snapshots.REPOSITORY_DECL_FILENAME).write_text(
        "  api-service  \n", encoding="utf-8"
    )
    assert source_snapshots.book_repository(book) == "api-service"
