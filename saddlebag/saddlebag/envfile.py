"""A minimal ``.env`` reader — just enough to pull one variable out as a password.

saddlebag imports credentials *one variable at a time*: the ``.env`` supplies a
single secret, and the credential's metadata (env, roles, surface) is supplied as
CLI flags. A ``.env`` is a flat ``KEY=value`` list and carries none of that
metadata, which is exactly why it cannot stand alone as a credential source.

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
"""

from __future__ import annotations

from pathlib import Path

_EXPORT = "export "


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
