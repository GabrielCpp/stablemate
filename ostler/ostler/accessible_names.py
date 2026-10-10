"""Whether a `name:` bullet states the accessible name a browser computes, or describes one."""

from __future__ import annotations

import re

_QUOTES = (('"', '"'), ("“", "”"), ("«", "»"))
_MARKS = (
    ("](", "a markdown link"),
    ("`", "a code span"),
    ('"', "a quoted label among other words"),
    ("“", "a quoted label among other words"),
    ("«", "a quoted label among other words"),
)
_TRANSLATION_KEY = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)+")
_CALL = re.compile(r"[A-Za-z_$][\w$.]*\(.*\)")
_CODE_EXPRESSION = re.compile(r"[a-z_$][\w$]*(?:\.[\w$]+)+|[a-z_$][a-z0-9_$]*[A-Z][\w$]*")


def literal_name(value: str) -> str:
    """*value* with one wrapping pair of quotes removed, the way a writer quotes a label."""
    text = value.strip()
    for opening, closing in _QUOTES:
        if len(text) > 1 and text.startswith(opening) and text.endswith(closing):
            return text[len(opening):-len(closing)].strip()
    return text


def prose_mark(value: str) -> str:
    """What marks the bullet *value*, as written, as a description of a name rather than the name, or `""`."""
    text = value.strip()
    spanned = len(text) > 1 and text.startswith("`") and text.endswith("`")
    if spanned:
        text = text[1:-1].strip()
        if _CODE_EXPRESSION.fullmatch(text):
            return "a code expression"
    literal = literal_name(text)
    if literal == text:
        if len(text) > 1 and text.startswith("(") and text.endswith(")"):
            return "a parenthetical description"
        if _TRANSLATION_KEY.fullmatch(text):
            return "a translation key"
        if _CALL.fullmatch(text):
            return "a call expression"
    return next((mark for token, mark in _MARKS if token in literal), "")
