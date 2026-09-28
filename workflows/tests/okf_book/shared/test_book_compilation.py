"""A compile states only the obligations of the books it names."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from workhorse_workflows.okf_book.shared.book_compilation import compile_services, obligation_page


def test_a_compile_states_only_the_named_books_obligations(app: Callable[[str], Path]) -> None:
    repo = app("globex")

    compiled = compile_services(repo, ("api-service",))

    assert compiled.obligations
    assert {obligation_page(obligation).split("/")[2] for obligation in compiled.obligations} == {"api-service"}
