from __future__ import annotations

from pathlib import Path

from okf_book.main.tally import ENDPOINT_PAGES, INLINE_SERVER, SERVER_PAGE, App, write_inline_server

from workhorse_workflows.okf_book.shared.book_shape import Carve, carve_inline_endpoints, carved_pages


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
