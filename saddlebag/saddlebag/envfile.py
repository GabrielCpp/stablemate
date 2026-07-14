"""A minimal ``.env`` reader and writer.

Two callers, one format. :func:`read_var` pulls a single variable out of a
``.env`` as a credential's password — the ``.env`` supplies the secret and the
metadata (env, roles, surface) comes from CLI flags, because a flat ``KEY=value``
list carries none of it. :func:`dumps` goes the other way, rendering an
environment's resolved entries back out as a ``.env`` file.

Deliberately no dependency on ``python-dotenv``. The value contract is kept
predictable for secrets:

* a line may be blank, a ``#`` comment, or ``KEY=value`` (an optional ``export``
  prefix is allowed);
* the value is everything after the first ``=``, with surrounding whitespace
  trimmed;
* if the trimmed value is wrapped in a matching pair of single or double quotes,
  those quotes are stripped and the inner text is taken **literally** — spaces
  and ``#`` included.

Inline comments after an unquoted value are *not* stripped: a password may
legitimately contain ``#``, so removing it would corrupt the secret. Quote any
value that contains spaces, ``#``, or leading/trailing whitespace.

:func:`dumps` is the exact inverse of :func:`parse`: it quotes whenever a bare
value would read back as something else, so ``parse(dumps(v)) == v`` for every
value it accepts. There is no escaping in the contract above, so the handful of
values it *cannot* represent raise rather than round-trip to something subtly
different — a corrupted secret is worse than a failed render.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

_EXPORT = "export "
_QUOTES = ("'", '"')
#: Characters that make a bare value parse back as something else.
_NEEDS_QUOTING = (" ", "\t", "#")


def parse(path: Path | str) -> dict[str, str]:
    """Parse a ``.env`` file into a dict. Later assignments win over earlier ones."""
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
    """Return the value of ``name`` in the ``.env`` at ``path``.

    Raises :class:`FileNotFoundError` if the file is missing, and :class:`KeyError`
    if the variable is absent (an *empty* value is returned as ``""`` — the caller
    decides whether that is acceptable).
    """
    env = parse(path)
    if name not in env:
        raise KeyError(name)
    return env[name]


def read_keys(path: Path | str) -> list[str]:
    """The variable names in a ``.env``, in file order — **values discarded**.

    This is what seeds an environment's key manifest from a checked-in
    ``.env.example``. Nothing is guessed and nothing is stored: the caller gets a
    list of names, every one of which lands ``pending`` until a human supplies it.
    """
    return list(parse(path))


def quote(value: str) -> str:
    """Render one value as a ``.env`` field that :func:`parse` reads back unchanged."""
    if "\n" in value or "\r" in value:
        raise ValueError("a dotenv value cannot contain a newline; use --format json")

    looks_quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in _QUOTES
    if not (looks_quoted or value != value.strip() or any(c in value for c in _NEEDS_QUOTING)):
        return value

    # parse() strips one matching pair and takes the inside literally, so the
    # wrapping quote simply has to be a character the value does not contain.
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
