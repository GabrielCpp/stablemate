from __future__ import annotations

from groom.tui.clean import clean


def test_an_osc_52_clipboard_write_is_removed_whole():
    assert clean("a\x1b]52;c;ZXZpbA==\x07b") == "ab"


def test_an_osc_closed_by_string_terminator_is_removed_whole():
    assert clean("a\x1b]52;c;ZXZpbA==\x1b\\b") == "ab"


def test_a_screen_clear_is_removed():
    assert clean("x\x1b[2Jy") == "xy"


def test_a_c1_csi_is_removed():
    assert clean("x\x9b2Jy") == "xy"


def test_a_lone_carriage_return_is_removed():
    assert clean("over\rwrite") == "overwrite"


def test_newline_and_tab_survive():
    assert clean("a\n\tb") == "a\n\tb"


def test_other_controls_and_c1_are_dropped():
    assert clean("a\x00\x07\x08\x7f\x85b") == "ab"


def test_a_two_byte_escape_is_removed():
    assert clean("a\x1bcb") == "ab"


def test_ordinary_markdown_is_untouched():
    text = "# Title\n\n- **bold** and `code`\n- [link](https://example.com)\n\n```py\nx = 1\n```\n"
    assert clean(text) == text


def test_none_becomes_an_empty_string():
    assert clean(None) == ""
