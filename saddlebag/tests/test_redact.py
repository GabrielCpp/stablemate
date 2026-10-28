"""The redactor: which forms of a value it masks, and that a value split across reads is still masked."""

from __future__ import annotations

import pytest

from saddlebag.redact import Redactor, forms

SECRET = 'p@ss$word"x'


def stream(redactor: Redactor, *chunks: bytes) -> bytes:
    return b"".join(redactor.feed(chunk) for chunk in chunks) + redactor.flush()


@pytest.mark.parametrize(
    "escaped",
    ['p@ss$word"x', 'p@ss$$word"x', "p%40ss%24word%22x", 'p@ss$word\\"x'],
)
def test_every_escaped_form_is_masked(escaped: str) -> None:
    assert escaped in forms(SECRET)
    text = f"DB_PASSWORD: {escaped}\n".encode()
    assert stream(Redactor([SECRET]), text) == b"DB_PASSWORD: [REDACTED]\n"


def test_quote_plus_form_is_masked() -> None:
    assert stream(Redactor(["two words!"]), b"q=two+words%21&") == b"q=[REDACTED]&"


@pytest.mark.parametrize("split", range(1, len(f"user={SECRET};") + 1))
def test_a_value_split_across_two_reads_is_masked(split: int) -> None:
    text = f"user={SECRET};".encode()
    assert stream(Redactor([SECRET]), text[:split], text[split:]) == b"user=[REDACTED];"


def test_a_value_fed_one_byte_at_a_time_is_masked() -> None:
    text = f"a {SECRET} b {SECRET} c".encode()
    chunks = [text[index:index + 1] for index in range(len(text))]
    assert stream(Redactor([SECRET]), *chunks) == b"a [REDACTED] b [REDACTED] c"


def test_output_without_a_value_passes_unchanged() -> None:
    text = b"nothing to see here\n" * 50
    assert stream(Redactor([SECRET]), text[:333], text[333:]) == text


def test_the_longer_of_two_overlapping_values_wins() -> None:
    assert stream(Redactor(["abcdefgh", "abcdefgh-longer"]), b"[abcdefgh-longer]") == b"[[REDACTED]]"


def test_a_redactor_with_no_value_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Redactor([""])
