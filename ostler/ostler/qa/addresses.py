"""The address book: the value each of an environment's named addresses has for one run."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from urllib.parse import urlsplit

from ostler._vendor.stablemate_core import base_cache

LEASE_ENV = "STABLEMATE_LEASE"
BOOK_ENV = "STABLEMATE_ADDRESS_BOOK"
SHARING_VALUES = ("shared", "per-run")

_TOKEN = re.compile(r"(?<![$\w])\{([a-z][a-z0-9-]*)\}")
_NAME = re.compile(r"[a-z][a-z0-9-]*")
_LEASE = re.compile(r"[a-z0-9][a-z0-9_-]*")


class AddressError(ValueError):
    """An address a command or a URL names has no value this run can read."""


def is_name(text: str) -> bool:
    """Whether *text* spells an address name a `{name}` reference can carry."""
    return bool(_NAME.fullmatch(text))


def lease_problem(lease: str) -> str:
    """Why *lease* cannot name a copy, or empty when it can."""
    if _LEASE.fullmatch(lease):
        return ""
    return ("a lease is lowercase letters, digits, `-` and `_`, starting with a letter or "
            "a digit, because it names the copy's containers and files")


def names_in(text: str) -> list[str]:
    """Every `{name}` reference in *text*, in order."""
    return _TOKEN.findall(text)


def substitute(text: str, book: Mapping[str, str]) -> str:
    """*text* with each `{name}` the book gives replaced by its value."""
    return _TOKEN.sub(lambda match: book.get(match.group(1), match.group(0)), text)


def is_address(value: str) -> bool:
    """Whether *value* is an absolute `http(s)://` URL a client can reach."""
    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def read_book(path: Path) -> dict[str, str]:
    """The book at *path* as ``{name: url}``."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AddressError(f"no address book at {path}: the bring-up has not written it") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AddressError(f"the address book at {path} is unreadable: {exc}") from exc
    if not isinstance(raw, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in raw.items()):
        raise AddressError(f"the address book at {path} is not a JSON object of name to URL")
    return {key: value.rstrip("/") for key, value in raw.items()}


def write_book(path: Path, book: Mapping[str, str]) -> None:
    """Write *book* to *path*, replacing what a previous bring-up wrote."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(book), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def book_problems(book: Mapping[str, str], names: Iterable[str]) -> list[str]:
    """Why *book* cannot serve an environment declaring *names*, one sentence per name."""
    problems = [f"it gives no address for `{name}`" for name in names if name not in book]
    problems += [f"its `{name}` is `{value}`, not an absolute http(s) URL"
                 for name, value in book.items() if not is_address(value)]
    return problems


def book_path(environment: Path, lease: str) -> Path:
    """Where the book for *environment* lives, one file per lease and one for the shared stack."""
    key = hashlib.sha256(str(environment.resolve()).encode()).hexdigest()[:12]
    leaf = f"lease-{lease}.json" if lease else "shared.json"
    return base_cache.cache_root() / "address-books" / key / leaf


def resolve_now(text: str, environ: Mapping[str, str] | None = None) -> str:
    """*text* with its `{name}` references read from this run's book at this moment."""
    if not names_in(text):
        return text
    where = (os.environ if environ is None else environ).get(BOOK_ENV, "")
    if not where:
        return text
    return substitute(text, read_book(Path(where)))


@contextlib.contextmanager
def leased(env: Mapping[str, str]) -> Iterator[None]:
    """Hold *env* in this process's environment, so every recipe a bring-up runs inherits it."""
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


__all__ = [
    "BOOK_ENV",
    "LEASE_ENV",
    "SHARING_VALUES",
    "AddressError",
    "book_path",
    "book_problems",
    "is_address",
    "is_name",
    "lease_problem",
    "leased",
    "names_in",
    "read_book",
    "resolve_now",
    "substitute",
    "write_book",
]
