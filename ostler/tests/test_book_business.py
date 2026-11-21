"""Business pages: rules above any one service, searched beside the service books."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest

from book_fakes import isolated_services
from ostler.book.business import cmd_business
from ostler.book.index import cmd_search_book

SHOP = '''
from ostler.book import Action, Arrange, Service, Stack
from ostler.book.domain import State


class Order(Action):
    """Opens a ceramic order."""


class Opens(Arrange[int]):
    does = "A customer opens a ceramic order."
    carries = Order


service = Service(name="shop", new_model=State, surface=lambda environment: None, journeys=(),
                  stack=lambda directory: Stack((), directory), outside=(Opens,))
'''

GLAZE = "date: 2026-11-21\nsources: operator, 2026-11-21\n\nA glaze is a ceramic coating fired onto a piece.\nIt is never a paint.\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _shop(root: Path) -> None:
    _write(root / "services" / "__init__.py", "")
    _write(root / "services" / "shop" / "__init__.py", "")
    _write(root / "services" / "shop" / "service.py", SHOP)


def _page(root: Path, slug: str, text: str) -> None:
    _write(root / "business" / f"{slug}.md", text)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    for tmp in isolated_services(tmp_path, monkeypatch):
        _shop(tmp)
        yield tmp


def _search(term: str, service: str | None = None, kind: str | None = None) -> int:
    return cmd_search_book(SimpleNamespace(service=service, term=term, kind=kind))


def test_search_finds_a_business_page_with_no_service(root: Path, capsys: pytest.CaptureFixture[str]):
    _page(root, "glaze", GLAZE)
    assert _search("fired onto") == 0
    out = capsys.readouterr().out
    assert "== business\n" in out
    assert "business  business/glaze.md:4\n    A glaze is a ceramic coating fired onto a piece.\n" in out


def test_search_finds_a_business_page_when_a_service_is_given(root: Path, capsys: pytest.CaptureFixture[str]):
    _page(root, "glaze", GLAZE)
    assert _search("ceramic", service="services.shop") == 0
    out = capsys.readouterr().out
    assert "== business\n" in out
    assert "business  business/glaze.md:4" in out
    assert "action" in out


def test_the_decision_kind_excludes_business_pages(root: Path, capsys: pytest.CaptureFixture[str]):
    _page(root, "glaze", GLAZE)
    assert _search("ceramic", kind="decision") == 1
    assert "business" not in capsys.readouterr().out.replace("nothing in the book says", "")


def test_the_business_kind_shows_only_business_pages(root: Path, capsys: pytest.CaptureFixture[str]):
    _page(root, "glaze", GLAZE)
    assert _search("ceramic", kind="business") == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "== business"
    assert "action" not in out
    assert "outside" not in out


def test_no_business_folder_leaves_the_output_unchanged(root: Path, capsys: pytest.CaptureFixture[str]):
    assert _search("ceramic") == 0
    out = capsys.readouterr().out
    assert "business" not in out
    assert "== services.shop" in out


def test_check_is_red_on_a_page_without_a_date(root: Path, capsys: pytest.CaptureFixture[str]):
    _page(root, "glaze", GLAZE)
    _page(root, "kiln", "sources: operator\n\nA kiln fires the piece.\n")
    assert cmd_business(SimpleNamespace(check=True), str(root)) == 1
    out = capsys.readouterr().out
    assert "business/kiln.md has no date: line" in out
    assert "glaze" not in out


def test_check_is_red_on_an_empty_body(root: Path, capsys: pytest.CaptureFixture[str]):
    _page(root, "kiln", "date: 2026-11-21\n\n")
    assert cmd_business(SimpleNamespace(check=True), str(root)) == 1
    assert "business/kiln.md has an empty body" in capsys.readouterr().out


def test_check_is_green_on_complete_pages_and_the_list_names_each(root: Path, capsys: pytest.CaptureFixture[str]):
    _page(root, "glaze", GLAZE)
    assert cmd_business(SimpleNamespace(check=True), str(root)) == 0
    assert capsys.readouterr().out == ""
    assert cmd_business(SimpleNamespace(check=False), str(root)) == 0
    assert capsys.readouterr().out == "glaze  2026-11-21  A glaze is a ceramic coating fired onto a piece.\n"
