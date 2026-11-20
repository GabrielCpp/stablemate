"""A step that crashes with no message still says which exception escaped it."""
from __future__ import annotations

from ostler.book.runner import crash_note


def test_an_exception_with_no_message_is_named_by_its_kind() -> None:
    assert crash_note(AssertionError()) == "crashed: AssertionError"


def test_a_message_gives_its_first_line() -> None:
    assert crash_note(ValueError("no such row\nand more")) == "crashed: ValueError: no such row"
