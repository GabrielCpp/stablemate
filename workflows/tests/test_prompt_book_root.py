"""A book path in a prompt names the book root, and every flow that renders one passes it."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from loaded_code import names, strings

import workhorse_workflows
from workhorse_workflows.coder.book_qa.flow import BookQa
from workhorse_workflows.coder.dev.flow import Dev
from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.shared.resolution import resolver_args

SOURCE = Path(workhorse_workflows.__file__).parent


def test_no_prompt_names_a_book_path_under_the_docs_root() -> None:
    offenders = [
        str(path.relative_to(SOURCE))
        for path in SOURCE.glob("**/prompts/*.md")
        if "workhorse_var('docs_root') }}/services" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_no_prompt_names_a_service_book_under_a_fixed_services_folder() -> None:
    offenders = [
        str(path.relative_to(SOURCE))
        for path in SOURCE.glob("coder/**/prompts/*.md")
        if re.search(r"\}\}/services/<name>|`services\.<name>`", path.read_text(encoding="utf-8"))
        or "workhorse_var('book_root') }}/services" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


@pytest.mark.parametrize(
    "owner",
    [Dev._story_args, BookQa._owner_args, Docs._spec_brief, Qa],  # pyright: ignore[reportPrivateUsage]
    ids=["dev", "book_qa", "docs", "qa"],
)
def test_every_flow_that_renders_book_root_passes_it(owner: Any) -> None:
    assert "book_root" in strings(owner)
    assert "find_book_root" in names(owner)


@pytest.mark.parametrize(
    "owner",
    [Dev._story_args, BookQa._owner_args, Docs._spec_brief, Qa, resolver_args],  # pyright: ignore[reportPrivateUsage]
    ids=["dev", "book_qa", "docs", "qa", "resolution"],
)
def test_every_flow_that_renders_service_books_passes_it(owner: Any) -> None:
    assert {"service_package", "service_books"} <= strings(owner)
    assert "package_folder" in names(owner)
