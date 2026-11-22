"""The other books an owner reads for the shape of each file are found under the book's own package."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.main.book_names import book_module, finished_books


def _book(root: Path, *parts: str) -> None:
    folder = root.joinpath(*parts)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "service.py").write_text("SERVICE = 1\n", encoding="utf-8")


def test_the_flat_package_lists_every_other_book(tmp_path: Path) -> None:
    _book(tmp_path, "services", "api")
    _book(tmp_path, "services", "ledger")
    _book(tmp_path, "services", "groom", "http")

    assert finished_books(tmp_path, "services", "ledger") == ["services/api", "services/groom"]


def test_a_repository_package_lists_only_its_own_books(tmp_path: Path) -> None:
    _book(tmp_path, "services", "acme", "api")
    _book(tmp_path, "services", "acme", "ledger")
    _book(tmp_path, "services", "acme", "groom", "http")
    _book(tmp_path, "services", "globex", "web")

    assert finished_books(tmp_path, "services.acme", "ledger") == ["services/acme/api", "services/acme/groom"]


def test_a_module_is_its_package_then_its_service() -> None:
    assert book_module("services.acme", "api") == "services.acme.api"
