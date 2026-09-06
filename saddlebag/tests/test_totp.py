"""RFC 6238 conformance, and the seed spellings a provider actually prints."""

from __future__ import annotations

import pytest

from saddlebag import totp

# RFC 6238 Appendix B: the seed is the ASCII "12345678901234567890" in base32, and
# the vectors pin one code per counter. They are the reason this implementation can
# be thirty lines with no dependency and still be trusted.
RFC_SEED = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


@pytest.mark.parametrize(
    ("moment", "expected"),
    [(59, "287082"), (1111111109, "081804"), (1111111111, "050471"), (1234567890, "005924")],
)
def test_matches_the_rfc_6238_vectors(moment: int, expected: str) -> None:
    assert totp.code(RFC_SEED, now=moment) == expected


@pytest.mark.parametrize("spelling", ["gezd gnbv gy3t qojq gezd gnbv gy3t qojq", "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"])
def test_accepts_the_seed_as_the_provider_prints_it(spelling: str) -> None:
    """Grouped and lower-case are how enrolment screens show a seed."""
    assert totp.code(spelling, now=59) == "287082"


def test_accepts_an_unpadded_seed() -> None:
    """A 16-character seed — GitHub's length — arrives without its base32 padding."""
    assert len(totp.code("VNHP5MU6JYZSS4G3", now=59)) == 6


def test_an_empty_seed_is_an_error_rather_than_a_valid_looking_code() -> None:
    """The failure that cost an afternoon: an empty keychain entry.

    ``secret-tool store`` reads from stdin, so a non-interactive shell stores the
    empty string; HMAC over an empty key computes perfectly well-formed codes that
    every verifier rejects. Refusing the seed is what turns that into a diagnosis.
    """
    with pytest.raises(totp.SeedError):
        totp.code("   ")


def test_a_seed_that_is_not_base32_is_an_error() -> None:
    with pytest.raises(totp.SeedError):
        totp.code("this-is-not-base32-1890")


def test_seconds_remaining_counts_down_within_the_window() -> None:
    assert totp.seconds_remaining(now=0) == 30
    assert totp.seconds_remaining(now=29) == 1
    assert totp.seconds_remaining(now=30) == 30
