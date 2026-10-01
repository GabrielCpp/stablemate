"""A compile states only the obligations of the books it names."""
from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from ostler import index

from workhorse_workflows.okf_book.shared.book_compilation import compile_services, obligation_node, obligation_page


def test_a_compile_states_only_the_named_books_obligations(app: Callable[[str], Path]) -> None:
    repo = app("globex")

    compiled = compile_services(repo, ("api-service",))

    assert compiled.obligations
    assert {obligation_page(obligation).split("/")[2] for obligation in compiled.obligations} == {"api-service"}


def test_a_compile_names_the_obligations_that_arrange_each_fixture(app: Callable[[str], Path]) -> None:
    repo = app("globex")
    page = repo / "docs/features/api-service/http/api-service.md"
    head, _, tail = page.read_text(encoding="utf-8").partition("### get-widgets")
    _ = page.write_text(f"{head}### get-widgets{tail.replace('- fixture:', '- fixture: seeded-widget', 1)}", encoding="utf-8")

    compiled = compile_services(repo, ("api-service",))

    assert list(compiled.arranging) == ["seeded-widget"]
    assert {obligation_node(obligation) for obligation in compiled.arranging["seeded-widget"]} == {
        "docs/features/api-service/http/api-service.md#get-widgets",
    }


def test_a_second_compile_of_an_unchanged_book_reads_every_page_from_the_index(
    app: Callable[[str], Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = app("globex")
    monkeypatch.setenv("OSTLER_INDEX_DIR", str(tmp_path / "index"))
    _ = compile_services(repo, ("api-service",))
    stores: list[index.IndexStore] = []
    opened = index.session

    @contextmanager
    def _session(root: Path) -> Generator[index.IndexStore]:
        with opened(root) as store:
            stores.append(store)
            yield store

    monkeypatch.setattr(index, "session", _session)

    _ = compile_services(repo, ("api-service",))

    assert stores[0].hits
    assert stores[0].misses == 0
