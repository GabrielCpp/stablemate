"""The catch-up reads the books of one package, and keeps a book's register in that package's folder."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.catch_up.nodes import book_modules
from workhorse_workflows.okf_book.catch_up.register import read_register, register_path, write_register


def _book(root: Path, *parts: str) -> None:
    folder = root.joinpath(*parts)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "service.py").write_text("SERVICE = 1\n", encoding="utf-8")


def test_the_flat_package_keys_each_book_by_its_folder(tmp_path: Path) -> None:
    _book(tmp_path, "services", "api")
    _book(tmp_path, "services", "groom", "http")
    _book(tmp_path, "services", "groom", "web")

    assert book_modules(tmp_path, "services") == {"api": ["services.api"], "groom": ["services.groom.http", "services.groom.web"]}


def test_a_repository_package_reads_only_its_own_books_by_bare_name(tmp_path: Path) -> None:
    _book(tmp_path, "services", "acme", "api")
    _book(tmp_path, "services", "acme", "groom", "http")
    _book(tmp_path, "services", "acme", "groom", "web")
    _book(tmp_path, "services", "globex", "web")

    assert book_modules(tmp_path, "services.acme") == {"api": ["services.acme.api"], "groom": ["services.acme.groom.http", "services.acme.groom.web"]}


def test_the_register_sits_in_the_package_folder(tmp_path: Path) -> None:
    assert register_path(tmp_path, "api") == tmp_path / "services" / "api" / "DECLINED.md"
    assert register_path(tmp_path, "api", "services.acme") == tmp_path / "services" / "acme" / "api" / "DECLINED.md"

    (tmp_path / "services" / "acme" / "api").mkdir(parents=True)
    _ = write_register(tmp_path, "api", ["screen A: nothing leads to it: never linked"], "services.acme")

    assert read_register(tmp_path, "api", "services.acme") == ["screen A: nothing leads to it: never linked"]
    assert read_register(tmp_path, "api") == []
