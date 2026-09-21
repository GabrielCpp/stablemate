"""A minimal ``.env`` reader and writer."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

_EXPORT = "export "
_QUOTES = ("'", '"')
_NEEDS_QUOTING = (" ", "\t", "#")


def parse(path: Path | str) -> dict[str, str]:
    """Parse a ``.env`` file into a dict."""
    result: dict[str, str] = {}
    text = Path(path).read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith(_EXPORT):
            line = line[len(_EXPORT) :].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[key] = value
    return result


def read_var(path: Path | str, name: str) -> str:
    """Return the value of ``name`` in the ``.env`` at ``path``."""
    env = parse(path)
    if name not in env:
        raise KeyError(name)
    return env[name]


def read_keys(path: Path | str) -> list[str]:
    """The variable names in a ``.env``, in file order — **values discarded**."""
    return list(parse(path))


def quote(value: str) -> str:
    """Render one value as a ``.env`` field that :func:`parse` reads back unchanged."""
    if "\n" in value or "\r" in value:
        raise ValueError("a dotenv value cannot contain a newline; use --format json")

    looks_quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in _QUOTES
    if not (looks_quoted or value != value.strip() or any(c in value for c in _NEEDS_QUOTING)):
        return value

    for q in ('"', "'"):
        if q not in value:
            return f"{q}{value}{q}"
    raise ValueError(
        "a dotenv value containing both ' and \" and needing quotes cannot be "
        "represented without escaping; use --format json"
    )


def dumps(values: Mapping[str, str]) -> str:
    """Render resolved entries as ``.env`` text, in the order given."""
    return "".join(f"{key}={quote(value)}\n" for key, value in values.items())
