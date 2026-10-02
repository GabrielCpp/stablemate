from __future__ import annotations

from pathlib import Path

import pytest
from okf_book.main.tally import (
    ENDPOINT_PAGES,
    INLINE_SERVER,
    LEDGER,
    OTHER_PAGE,
    SERVER_PAGE,
    SMALL_LIMIT,
    App,
    write_inline_server,
)
from ostler import fragment_carve

from workhorse_workflows.okf_book.shared import book_shape
from workhorse_workflows.okf_book.shared.book_shape import (
    Carve,
    carve_inline_endpoints,
    carve_oversized_pages,
    carved_pages,
    shape_book,
)


def test_each_endpoint_a_server_page_holds_inline_is_carved_onto_its_own_page(app: App) -> None:
    repo = app("tally-cli")
    write_inline_server(repo)

    carves = carve_inline_endpoints(repo, "tally")

    assert carves == (Carve(SERVER_PAGE, (*ENDPOINT_PAGES, SERVER_PAGE)),)
    assert carved_pages(carves) == (*ENDPOINT_PAGES, SERVER_PAGE)
    assert "### " not in (repo / SERVER_PAGE).read_text(encoding="utf-8")
    assert all((repo / page).is_file() for page in ENDPOINT_PAGES)


def test_a_book_with_no_inline_endpoint_is_left_as_it_is(app: App) -> None:
    repo = app("tally-cli")

    assert carve_inline_endpoints(repo, "tally") == ()


def test_a_server_page_in_another_book_is_not_carved(app: App) -> None:
    repo = app("tally-cli")
    write_inline_server(repo)

    assert carve_inline_endpoints(repo, "ledger") == ()
    assert (repo / SERVER_PAGE).read_text(encoding="utf-8") == INLINE_SERVER


def test_a_carve_that_would_change_a_page_someone_left_uncommitted_is_not_made(app: App) -> None:
    repo = app("tally-cli")
    write_inline_server(repo)

    carves = carve_inline_endpoints(repo, "tally", frozenset({SERVER_PAGE}))

    assert carves == (Carve(SERVER_PAGE, refusal=f"it would change pages someone left uncommitted: {SERVER_PAGE}"),)
    assert (repo / SERVER_PAGE).read_text(encoding="utf-8") == INLINE_SERVER
    assert not any((repo / page).exists() for page in ENDPOINT_PAGES)


def test_a_carve_ostler_refuses_is_reported_and_writes_nothing(app: App) -> None:
    repo = app("tally-cli")
    write_inline_server(repo)
    taken = Path(repo / ENDPOINT_PAGES[1])
    _ = taken.write_text("taken\n", encoding="utf-8")

    carves = carve_inline_endpoints(repo, "tally")

    assert carves == (Carve(SERVER_PAGE, refusal="a page already exists for: get-total"),)
    assert (repo / SERVER_PAGE).read_text(encoding="utf-8") == INLINE_SERVER


@pytest.fixture
def small_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(book_shape, "PAGE_SIZE_LIMIT", SMALL_LIMIT)
    monkeypatch.setattr(fragment_carve, "PAGE_SIZE_LIMIT", SMALL_LIMIT)


def test_a_page_past_the_limit_is_carved_onto_fragments_that_fit(app: App, small_limit: None) -> None:
    repo = app("tally-cli")
    _ = (repo / OTHER_PAGE).write_text(LEDGER, encoding="utf-8")

    [carve] = [c for c in carve_oversized_pages(repo, "tally") if c.page == OTHER_PAGE]

    assert carve.page == OTHER_PAGE and not carve.refusal
    fragments = [p for p in carve.pages if p != OTHER_PAGE]
    assert fragments and OTHER_PAGE in carve.pages
    assert all((repo / p).stat().st_size <= SMALL_LIMIT for p in carve.pages)


def test_a_page_within_the_limit_is_not_carved(app: App, small_limit: None) -> None:
    repo = app("tally-cli")

    assert all(c.page != OTHER_PAGE for c in carve_oversized_pages(repo, "tally"))
    assert "### rule-" not in (repo / OTHER_PAGE).read_text(encoding="utf-8")


def test_shaping_a_book_carves_its_inline_endpoints_and_its_oversized_pages(app: App, small_limit: None) -> None:
    repo = app("tally-cli")
    write_inline_server(repo)
    _ = (repo / OTHER_PAGE).write_text(LEDGER, encoding="utf-8")

    carves = shape_book(repo, "tally")

    written = [c.page for c in carves if c.pages]
    assert written[0] == SERVER_PAGE and OTHER_PAGE in written[1:]
    assert set(ENDPOINT_PAGES) <= set(carved_pages(carves))
