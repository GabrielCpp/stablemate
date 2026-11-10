"""What a book may declare unseen: an answer, a field of one, or the input classes."""

from __future__ import annotations

from typing import Any, cast

import pytest

from ostler.book import Answer, Endpoint
from ostler.book.errors import BookError
from ostler.book.witness import Because, Unseen


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
