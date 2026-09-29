"""A compile states only the obligations of the books it names."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

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
