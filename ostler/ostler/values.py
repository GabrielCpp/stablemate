"""The grammars declared on ``BulletKey.value_kind`` — one parser per kind, never a second one."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from ostler.qa.compile_http import HTTP_METHODS
from ostler.qa.runbook import bullet_text


def _url(value: str) -> str:
    parts = urlsplit(bullet_text(value))
    if parts.scheme in ("http", "https") and parts.netloc:
        return ""
    return "it is not an absolute `http(s)://` URL"


def _http_method(value: str) -> str:
    if bullet_text(value).upper() in HTTP_METHODS:
        return ""
    return "it does not spell one of " + "/".join(HTTP_METHODS)


def _checkout_path(value: str) -> str:
    path = PurePosixPath(bullet_text(value))
    if path.is_absolute():
        return "it is an absolute path, and a step's directory is read from the checkout root"
    if ".." in path.parts:
        return "it climbs out of the checkout with `..`"
    return ""


VALUE_KINDS: dict[str, Callable[[str], str]] = {
    "url": _url,
    "http-method": _http_method,
    "checkout-path": _checkout_path,
}
