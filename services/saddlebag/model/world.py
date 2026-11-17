"""What the model reads off the store: the values it holds, the dotenv it keeps and how a dotenv line is judged."""

from __future__ import annotations

from . import words
from .files import DOTENV
from .state import Store


def stored(s: Store) -> set[str]:
    """Every stored password and TOTP seed, in each of the forms a tool escapes it."""
    held: set[str] = set()
    for secret in s.secrets:
        for field in ("password", "totp"):
            value = secret.value(field)
            if value:
                held |= words.forms(value)
    return held


def registered(s: Store) -> set[str]:
    return {secret.var for secret in s.secrets if secret.var}


def verdict(s: Store, key: str, value: str) -> str | None:
    """The rule that makes this dotenv line secret, or None."""
    if value and value in stored(s):
        return "held-value"
    if key in registered(s):
        return "registered-var"
    return words.shape_rule(key, value)


def lines(s: Store, path: str = DOTENV) -> list[str]:
    record = s.files.get(path)
    return list(record.holds) if record is not None else []


def entries(s: Store, path: str = DOTENV) -> list[tuple[str, str]]:
    return [pair for pair in (words.key_of(line) for line in lines(s, path)) if pair is not None]
