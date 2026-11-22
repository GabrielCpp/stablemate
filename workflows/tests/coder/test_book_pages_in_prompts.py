"""Each turn that judges or writes against the product's rules is sent to the product, team and company books."""
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


def _flat(prompt: str, **args: str) -> str:
    return " ".join(_render(prompt, **args).split())


LEVELS = ("company", "team", "product", "decision")


@pytest.mark.parametrize("kind", LEVELS)
@pytest.mark.parametrize("prompt", SEARCHING.values(), ids=SEARCHING.keys())
def test_a_turn_searches_each_book_by_kind(prompt: str, kind: str) -> None:
    assert f"--kind {kind}" in _render(prompt)


@pytest.mark.parametrize("prompt", SEARCHING.values(), ids=SEARCHING.keys())
def test_a_turn_no_longer_searches_the_old_kind(prompt: str) -> None:
    assert "--kind business" not in _render(prompt)


@pytest.mark.parametrize("prompt", READING.values(), ids=READING.keys())
def test_a_turn_lists_the_pages_and_reads_each(prompt: str) -> None:
    text = _render(prompt, book_root="/book")
    assert "ostler book pages" in text
    assert "/business/" not in text


@pytest.mark.parametrize("prompt", ["book_qa/prompts/qa-review.md", "shared/prompts/resolve-operator.md"])
def test_a_judging_turn_states_the_order_of_authority(prompt: str) -> None:
    assert "company, team, product, service decision, story" in _flat(prompt, book_root="/book")


def test_the_review_reports_a_conflict_between_levels() -> None:
    assert "report the conflict and settle neither side" in _render("book_qa/prompts/qa-review.md")


def test_the_resolver_never_settles_a_conflict_between_levels() -> None:
    assert "you do not settle it" in _flat("shared/prompts/resolve-operator.md", book_root="/book")


def test_the_resolver_writes_a_rule_that_outlives_the_story_to_the_product_book() -> None:
    text = _render("shared/prompts/resolve-operator.md", book_root="/book")
    assert "`/book/product/<slug>.md`" in text
    assert "sources: operator, <date>" in text


def test_the_resolver_marks_a_product_page_that_may_belong_to_the_team_book() -> None:
    text = _render("shared/prompts/resolve-operator.md", book_root="/book")
    assert "sources: operator, <date>; may belong to the team book" in " ".join(text.split())
    assert "You never write a team or a company page" in " ".join(text.split())


def test_the_review_reports_a_criterion_that_contradicts_a_page() -> None:
    assert "contradicts a company, team or product page" in _render("book_qa/prompts/qa-review.md")


def test_the_review_never_cites_a_step_that_observed_nothing() -> None:
    text = _render("book_qa/prompts/qa-review.md")
    assert "model, app and result cells are empty observed nothing" in text
