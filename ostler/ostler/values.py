"""The grammars declared on ``BulletKey.value_kind`` — one parser per kind, never a second one."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

from ostler.qa.compile import _HTTP_METHODS
from ostler.qa.runbook import bullet_text


def _url(value: str) -> str:
    parts = urlsplit(bullet_text(value))
    if parts.scheme in ("http", "https") and parts.netloc:
        return ""
    return "it is not an absolute `http(s)://` URL"


def _http_method(value: str) -> str:
    if bullet_text(value).upper() in _HTTP_METHODS:
        return ""
    return "it does not spell one of " + "/".join(_HTTP_METHODS)


VALUE_KINDS: dict[str, Callable[[str], str]] = {
    "url": _url,
    "http-method": _http_method,
}
