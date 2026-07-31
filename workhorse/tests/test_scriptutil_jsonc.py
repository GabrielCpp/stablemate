"""Tests for scriptutil.load_jsonc — the reader for VSCode `.code-workspace` files.

The version this replaces stripped comments with `re.sub(r"//[^\n]*", "", text)`, which
does not know what a string literal is. Any workspace file holding a URL — and they
routinely do, alongside `//` in paths — was truncated mid-string and then reported to the
operator as invalid JSON. These pin that a real JSON5 parse reads the lenient syntax the
format actually allows *and* leaves string contents alone.
"""
from __future__ import annotations

import pytest

from workhorse.scriptutil import load_jsonc


def test_a_url_in_a_string_is_not_a_comment():
    """The confirmed defect: `https://` was cut at the `//`."""
    assert load_jsonc('{"url": "https://example.com", "trailing": 1,}') == {
        "url": "https://example.com",
        "trailing": 1,
    }


def test_a_double_slash_path_in_a_string_survives():
    text = '{"folders": [{"path": "//server/share/api-service"}]}'
    assert load_jsonc(text) == {"folders": [{"path": "//server/share/api-service"}]}


def test_line_and_block_comments_are_still_honored():
    text = """{
        // the repos this workspace opens
        "folders": [
            {"path": "api-service"}, /* second one lands later */
        ],
    }"""
    assert load_jsonc(text) == {"folders": [{"path": "api-service"}]}


def test_genuinely_broken_input_still_raises():
    """Strict, deliberately: `json-repair` would invent a parse for an operator's typo."""
    with pytest.raises(ValueError):
        load_jsonc('{"folders": [')


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
