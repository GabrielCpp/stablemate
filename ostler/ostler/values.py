"""The grammars declared on ``BulletKey.value_kind`` — one parser per kind, never a second one."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit

from ostler.qa.compile_http import HTTP_METHODS
from ostler.qa.runbook import bullet_text

_NAMED_ORIGIN = re.compile(r"^\{[a-z][a-z0-9-]*\}")


def _url(value: str) -> str:
    parts = urlsplit(_NAMED_ORIGIN.sub("http://named", bullet_text(value), count=1))
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


DIALOG_ANSWERS = ("accept", "dismiss")


def dialog_answer(value: str) -> str:
    """How a `dialog:` bullet answers the browser's dialog: its first word, before any reason."""
    words = bullet_text(value).split()
    return words[0].lower() if words else ""


def _dialog_answer(value: str) -> str:
    if dialog_answer(value) in DIALOG_ANSWERS:
        return ""
    return "it answers with neither " + " nor ".join(f"`{answer}`" for answer in DIALOG_ANSWERS)


GRPC_CODES = (
    "OK", "CANCELLED", "UNKNOWN", "INVALID_ARGUMENT", "DEADLINE_EXCEEDED", "NOT_FOUND",
    "ALREADY_EXISTS", "PERMISSION_DENIED", "RESOURCE_EXHAUSTED", "FAILED_PRECONDITION",
    "ABORTED", "OUT_OF_RANGE", "UNIMPLEMENTED", "INTERNAL", "UNAVAILABLE", "DATA_LOSS",
    "UNAUTHENTICATED",
)

_RPC_NAME = re.compile(r"^([a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*\.)?[A-Z][A-Za-z0-9]*/[A-Z][A-Za-z0-9]*$")


def _grpc_url(value: str) -> str:
    parts = urlsplit(bullet_text(value))
    if parts.scheme == "grpc" and parts.hostname and parts.port is not None:
        return ""
    return "it is not an absolute `grpc://host:port` address"


def _grpc_code(value: str) -> str:
    words = bullet_text(value).split()
    if words and words[0] in GRPC_CODES:
        return ""
    return "it does not open with one of the 17 canonical gRPC code names, such as `NOT_FOUND`"


def _rpc_name(value: str) -> str:
    if _RPC_NAME.match(bullet_text(value)):
        return ""
    return "it is not `package.Service/Method`, a lower snake package and PascalCase Service and Method"


def _entry_url(value: str) -> str:
    if not _url(value) or not _grpc_url(value):
        return ""
    return "it is neither an absolute `http(s)://` URL nor a `grpc://host:port` address"


VALUE_KINDS: dict[str, Callable[[str], str]] = {
    "url": _url,
    "http-method": _http_method,
    "checkout-path": _checkout_path,
    "dialog-answer": _dialog_answer,
    "grpc-url": _grpc_url,
    "entry-url": _entry_url,
    "grpc-code": _grpc_code,
    "rpc-name": _rpc_name,
}
