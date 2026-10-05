"""Whether a `name:` bullet states the accessible name a browser computes, or describes one."""

from __future__ import annotations

_QUOTES = (('"', '"'), ("“", "”"), ("«", "»"))
_MARKS = (
    ("](", "a markdown link"),
    ("`", "a code span"),
    ('"', "a quoted label among other words"),
    ("“", "a quoted label among other words"),
    ("«", "a quoted label among other words"),
)


def literal_name(value: str) -> str:
    """*value* with one wrapping pair of quotes removed, the way a writer quotes a label."""
    text = value.strip()
    for opening, closing in _QUOTES:
        if len(text) > 1 and text.startswith(opening) and text.endswith(closing):
            return text[len(opening):-len(closing)].strip()
    return text


def prose_mark(value: str) -> str:
    """What marks *value* as a description of a name rather than the name itself, or `""`."""
    text = literal_name(value)
    return next((mark for token, mark in _MARKS if token in text), "")
