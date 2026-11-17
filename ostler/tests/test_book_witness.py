"""What a book may declare unseen: an answer, a field of one, or the input classes."""

from __future__ import annotations

from typing import Any, cast

import pytest

from ostler.book import Answer, Endpoint
from ostler.book.errors import BookError
from ostler.book.witness import Because, Gap, Unseen, WitnessReport


class Ping(Endpoint):
    path = "/ping"
    answers = (Answer(200, None, "pong"),)


@pytest.mark.parametrize("item", ["401", "NOT_FOUND", "200: a.b", "OK: a.b", "inputs"])
def test_unseen_accepts_an_answer_a_field_or_the_input_classes(item: str):
    assert Unseen(Ping, item, Because.RUNTIME, "the runtime cannot send it").item == item


@pytest.mark.parametrize("item", ["it never happens", "401 unauthorized", "200:", "not_found", ""])
def test_unseen_refuses_free_text(item: str):
    with pytest.raises(BookError, match="write an answer"):
        Unseen(Ping, item, Because.RUNTIME, "a reason")


def test_unseen_refuses_a_reason_that_is_not_a_because():
    with pytest.raises(BookError, match="give a Because"):
        Unseen(Ping, "401", cast(Any, "no time"), "a reason")


def test_unseen_refuses_a_blank_why():
    with pytest.raises(BookError, match="say why"):
        Unseen(Ping, "401", Because.RUNTIME, "  ")


def _report(paths: list[str]) -> WitnessReport:
    gap = Gap(Ping, fields={200: paths})
    return WitnessReport([gap], 0, 1, 0, len(paths))


def test_forty_never_seen_paths_are_all_listed() -> None:
    paths = [f"f{n}" for n in range(40)]
    text = _report(paths).text("book")
    assert "- 200: fields never seen with a real value: " + ", ".join(paths) + "\n" in text + "\n"
    assert "more under" not in text


def test_more_than_forty_never_seen_paths_name_the_rest_by_first_segment() -> None:
    paths = [f"f{n}" for n in range(40)] + ["b.x.y", "a[].z", "a[].w", "c{}.k", "c{}"]
    text = _report(paths).text("book")
    assert "- 200: fields never seen with a real value: " + ", ".join(paths[:40]) + ", and 5 more under: a[], b, c{}\n" in text + "\n"
