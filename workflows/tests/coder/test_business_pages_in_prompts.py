"""Each turn that judges or writes against the product's rules is sent to the business pages."""
from __future__ import annotations

from pathlib import Path

import pytest
from workhorse.runner.backends.null import NullBackend
from workhorse.runner.ladder import AgentRunner
from workhorse.runner.spec import AgentNode

from workhorse_workflows import coder

SEARCHING = {
    "book-qa-review": "book_qa/prompts/qa-review.md",
    "book-qa": "book_qa/prompts/qa-book.md",
    "resolve-operator": "shared/prompts/resolve-operator.md",
}

READING = {
    "dev-plan": "dev/prompts/dev-plan.md",
    "docs": "docs/prompts/specify-story.md",
}


def _render(prompt: str, **args: str) -> str:
    node = AgentNode(type="agent", id="owner", prompt=prompt, timeout=420.0)
    return AgentRunner(backend=NullBackend()).render(node, args, Path(coder.__file__).parent).prompt


@pytest.mark.parametrize("prompt", SEARCHING.values(), ids=SEARCHING.keys())
def test_a_turn_searches_the_business_pages_by_kind(prompt: str) -> None:
    assert "--kind business" in _render(prompt)


@pytest.mark.parametrize("prompt", SEARCHING.values(), ids=SEARCHING.keys())
def test_a_turn_searches_the_decisions_by_kind(prompt: str) -> None:
    assert "--kind decision" in _render(prompt)


@pytest.mark.parametrize("prompt", READING.values(), ids=READING.keys())
def test_a_turn_reads_every_business_page(prompt: str) -> None:
    assert "/business/" in _render(prompt, book_root="/book")


def test_the_resolver_writes_a_rule_that_outlives_the_story_as_a_business_page() -> None:
    text = _render("shared/prompts/resolve-operator.md", book_root="/book")
    assert "`/book/business/<slug>.md`" in text
    assert "sources: operator, <date>" in text


def test_the_review_reports_a_criterion_that_contradicts_a_business_page() -> None:
    assert "contradicts a business page" in _render("book_qa/prompts/qa-review.md")


def test_the_review_never_cites_a_step_that_observed_nothing() -> None:
    text = _render("book_qa/prompts/qa-review.md")
    assert "model, app and result cells are empty observed nothing" in text
