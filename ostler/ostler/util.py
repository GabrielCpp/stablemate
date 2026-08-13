"""Small runtime compatibility helpers for the local Ostler checkout."""

from collections.abc import Mapping
from typing import Any, TypeGuard


def is_mapping(value: Any) -> TypeGuard[Mapping[str, Any]]:
    """Return whether a decoded value is a mapping."""
    return isinstance(value, Mapping)
