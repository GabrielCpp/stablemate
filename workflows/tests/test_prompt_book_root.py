"""A book path in a prompt names the book root, and every flow that renders one passes it."""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

import workhorse_workflows
from workhorse_workflows.coder.book_qa.flow import BookQa
from workhorse_workflows.coder.dev.flow import Dev
from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.qa.flow import Qa

SOURCE = Path(workhorse_workflows.__file__).parent


def test_no_prompt_names_a_book_path_under_the_docs_root() -> None:
    offenders = [
        str(path.relative_to(SOURCE))
        for path in SOURCE.glob("**/prompts/*.md")
        if "workhorse_var('docs_root') }}/services" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


@pytest.mark.parametrize(
    "owner",
    [Dev._story_args, BookQa._owner_args, Docs._spec_brief, Qa],  # pyright: ignore[reportPrivateUsage]
    ids=["dev", "book_qa", "docs", "qa"],
)
def test_every_flow_that_renders_book_root_passes_it(owner: Any) -> None:
    assert '"book_root": str(find_book_root(self.repo_dir))' in inspect.getsource(owner)
