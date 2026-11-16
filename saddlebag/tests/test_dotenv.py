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


ROUND_TRIP = ["8080", "", "a b", "it's", "a#b c", "$HOME", 'say "hi"', "/tmp/x.y-z_1"]


def test_an_assigned_value_reads_back_unchanged() -> None:
    for value in ROUND_TRIP:
        text, _ = dotenv.assign("A=old\n", "A", value)
        assert only(text.rstrip("\n")).value == value, (value, text)


def test_assign_keeps_export_spacing_comment_and_line_ending() -> None:
    text, found = dotenv.assign("# head\r\nexport  PORT = 80 # http\r\nOTHER='x' # keep\r\n", "PORT", "8080")
    assert found
    assert text == "# head\r\nexport  PORT = 8080 # http\r\nOTHER='x' # keep\r\n"


def test_assign_keeps_the_comment_after_a_quoted_value() -> None:
    text, _ = dotenv.assign("A='old value' # why\n", "A", "new")
    assert text == "A=new # why\n"


def test_assign_sets_every_assignment_of_the_key() -> None:
    text, _ = dotenv.assign("A=1\nB=2\nA=3\n", "A", "9")
    assert text == "A=9\nB=2\nA=9\n"


def test_assign_appends_a_missing_key_on_its_own_line() -> None:
    assert dotenv.assign("A=1", "B", "2") == ("A=1\nB=2\n", False)
    assert dotenv.assign("", "B", "2") == ("B=2\n", False)


def test_a_value_no_quoting_can_carry_is_refused() -> None:
    for value in ("two\nlines", "both ' and \""):
        try:
            dotenv.quote(value)
        except ValueError:
            continue
        raise AssertionError(value)
