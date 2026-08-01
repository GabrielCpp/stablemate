"""Narrowing helpers for data that came off disk untyped.

`yaml.safe_load` and `json.load` hand back `Any`, and every validator in this package opens
by asking what shape a value actually has. `isinstance(value, dict)` answers that at runtime,
but it narrows to a mapping whose *key* type is still unknown — so the very next
`value["id"]` reads as a lookup no key could satisfy, and a checker is right to say so. These
say the same thing in a form that survives to the subscript: a mapping parsed out of a YAML
or JSON document has string keys.

They are deliberately not validators. `is_mapping` says "this is a mapping", not "this is a
well-formed step"; the surrounding function still has to check the fields it needs, and the
problem strings it appends are the real contract.
"""

from __future__ import annotations

from typing import Any, TypeGuard


def is_mapping(value: object) -> TypeGuard[dict[str, Any]]:
    """``value`` is a loaded mapping — a YAML block, or a JSON object."""
    return isinstance(value, dict)


def is_sequence(value: object) -> TypeGuard[list[Any]]:
    """``value`` is a loaded list — a YAML sequence, or a JSON array.

    A `str` is not one: it is iterable, which is exactly how a scalar written where a list
    was meant gets silently walked one character at a time.
    """
    return isinstance(value, list)
