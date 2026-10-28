"""The dotenv reader: keys, unquoted values and the masked line."""

from __future__ import annotations

from saddlebag import dotenv


def only(text: str) -> dotenv.Line:
    (line,) = dotenv.parse(text)
    return line


def test_a_plain_assignment_has_a_key_and_a_value() -> None:
    line = only("APP_HOST=localhost")
    assert (line.key, line.value) == ("APP_HOST", "localhost")


def test_single_and_double_quotes_are_stripped() -> None:
    assert only("A='x y'").value == "x y"
    assert only('A="x y"').value == "x y"


def test_an_export_prefix_is_accepted() -> None:
    line = only("export TOKEN=abc")
    assert (line.key, line.value) == ("TOKEN", "abc")


def test_an_inline_comment_after_an_unquoted_value_is_dropped() -> None:
    assert only("A=abc # note").value == "abc"
    assert only("A='abc # kept'").value == "abc # kept"
    assert only("A=ab#c").value == "ab#c"


def test_an_empty_value_is_an_empty_string() -> None:
    line = only("KEY=")
    assert (line.key, line.value) == ("KEY", "")


def test_blank_comment_and_assignmentless_lines_have_no_key() -> None:
    lines = dotenv.parse("\n# note\nnot an assignment\n")
    assert [line.key for line in lines] == [None, None, None]
    assert [line.raw for line in lines] == ["", "# note", "not an assignment"]


def test_mask_keeps_the_export_prefix_and_key() -> None:
    assert dotenv.mask(only("export KEY='s3cret value'")) == "export KEY=[REDACTED]"
    assert dotenv.mask(only("KEY = abc")) == "KEY = [REDACTED]"


def test_mask_leaves_a_line_without_a_key_alone() -> None:
    assert dotenv.mask(only("# note")) == "# note"
