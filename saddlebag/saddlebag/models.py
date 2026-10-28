"""The secret record and its tags. Nothing here holds a stored value."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

FIELDS = ("username", "password", "totp")
VALUE_FIELDS = ("password", "totp")

Tag = tuple[str, str]

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_VAR = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_META_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
META_PREFIX = "meta."


def validate_name(name: str) -> str:
    """The secret name, or a ValueError saying what a name may contain."""
    if not _NAME.fullmatch(name):
        raise ValueError(f"invalid secret name {name!r}: use letters, digits, '.', '_' and '-'")
    return name


def validate_var(var: str) -> str:
    """The environment variable name, or a ValueError."""
    if not _VAR.fullmatch(var):
        raise ValueError(f"invalid environment variable name {var!r}")
    return var


def validate_meta_key(key: str) -> str:
    """The metadata key, or a ValueError saying what a key may contain."""
    if not _META_KEY.fullmatch(key):
        raise ValueError(f"invalid metadata key {key!r}: use letters, digits, '_' and '-', with no '.' or '='")
    return key


def validate_field(name: str, allowed: tuple[str, ...] = FIELDS) -> str:
    """The field name, or a ValueError listing the allowed ones. ``meta.<key>`` is allowed with the full FIELDS."""
    if name in allowed:
        return name
    if allowed == FIELDS and name.startswith(META_PREFIX):
        validate_meta_key(name[len(META_PREFIX) :])
        return name
    expected = ", ".join(allowed) + (f" or {META_PREFIX}<key>" if allowed == FIELDS else "")
    raise ValueError(f"unknown field {name!r}: expected one of {expected}")


def parse_tag(text: str) -> Tag:
    """Split ``key=value`` into a pair."""
    key, sep, value = text.partition("=")
    key, value = key.strip(), value.strip()
    if not sep or not key or not value:
        raise ValueError(f"invalid tag {text!r}: expected key=value")
    return key, value


def parse_meta(text: str) -> tuple[str, str]:
    """Split ``key=value`` into a pair."""
    key, sep, value = text.partition("=")
    key, value = key.strip(), value.strip()
    if not sep or not key or not value:
        raise ValueError(f"invalid metadata {text!r}: expected key=value")
    return validate_meta_key(key), value


def matches(tags: Iterable[Tag], wanted: Iterable[Tag]) -> bool:
    """Whether every wanted pair is among ``tags``."""
    return set(wanted) <= set(tags)


@dataclass(frozen=True)
class Secret:
    """A named secret: metadata plus which stored values exist."""

    name: str
    username: str | None = None
    description: str | None = None
    var: str | None = None
    tags: frozenset[Tag] = field(default_factory=frozenset)
    fields: frozenset[str] = field(default_factory=frozenset)
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """The JSON form. It names which values exist and never carries one."""
        return {
            "name": self.name,
            "username": self.username,
            "description": self.description,
            "var": self.var,
            "tags": [list(pair) for pair in sorted(self.tags)],
            "fields": sorted(self.fields),
            "metadata": dict(sorted(self.metadata.items())),
        }
