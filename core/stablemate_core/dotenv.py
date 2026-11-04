"""The dotenv assignment syntax every reader of a dotenv file agrees on."""

from __future__ import annotations

import re

_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_EXPORT = re.compile(r"export\s+")
_COMMENT = re.compile(r"\s+#.*$")


def unquote(text: str) -> str:
    """A dotenv value without its quotes, or without its trailing comment when unquoted."""
    if text[:1] in ("'", '"'):
        end = text.find(text[0], 1)
        return text[1:end] if end > 0 else text[1:]
    return _COMMENT.sub("", text).strip()


def assignment(raw: str) -> tuple[str, str] | None:
    """The ``(key, value)`` a dotenv line assigns, or ``None`` for a blank, comment or non-assignment line."""
    text = raw.strip()
    if not text or text.startswith("#"):
        return None
    if match := _EXPORT.match(text):
        text = text[match.end():]
    key, sep, rest = text.partition("=")
    key = key.strip()
    if not sep or not _KEY.fullmatch(key):
        return None
    return key, unquote(rest.strip())
