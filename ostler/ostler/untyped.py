"""Narrowing helpers for data that came off disk untyped, and the JSON value type it narrows to."""

from __future__ import annotations

from typing import Any, TypeGuard

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def is_mapping(value: object) -> TypeGuard[dict[str, Any]]:
    """``value`` is a loaded mapping — a YAML block, or a JSON object."""
    return isinstance(value, dict)


def is_sequence(value: object) -> TypeGuard[list[Any]]:
    """``value`` is a loaded list — a YAML sequence, or a JSON array."""
    return isinstance(value, list)
