from __future__ import annotations

import pytest

from stablemate_core.dotenv import assignment, unquote


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("KEY=value", ("KEY", "value")),
        ("export KEY = 'a # b'", ("KEY", "a # b")),
        ('KEY="x"  # note', ("KEY", "x")),
        ("KEY=plain # note", ("KEY", "plain")),
        ("KEY=", ("KEY", "")),
        ("# KEY=1", None),
        ("", None),
        ("no equals", None),
        ("1BAD=1", None),
    ],
)
def test_a_line_yields_its_assignment_or_nothing(raw, expected) -> None:
    assert assignment(raw) == expected


def test_an_unterminated_quote_keeps_the_rest() -> None:
    assert unquote("'abc") == "abc"
