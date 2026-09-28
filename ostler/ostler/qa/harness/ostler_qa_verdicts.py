"""The verdict a check returns, the arguments it reads, and the values its assert record carries."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ostler_qa_paths import JsonScalar, JsonValue


type CheckValue = str | int | float | bool | list[str]
type Args = Mapping[str, CheckValue]


def str_arg(args: Args, key: str) -> str:
    """The string a check's `key` argument holds, which the check's declaration types as one."""
    value = args[key]
    if not isinstance(value, str):
        raise TypeError(f"`{key}` must be a string, not {type(value).__name__}")
    return value


def scalar_arg(args: Args, key: str) -> JsonScalar:
    """The scalar a check's `key` argument holds, which the check's declaration types as one."""
    value = args[key]
    if isinstance(value, list):
        raise TypeError(f"`{key}` must be a scalar, not a list")
    return value


def strings_arg(args: Args, key: str) -> list[str]:
    """The strings a check's optional `key` argument lists, none when it is absent."""
    value = args.get(key, [])
    if not isinstance(value, list):
        raise TypeError(f"`{key}` must be a list of strings, not {type(value).__name__}")
    return value


@dataclass(frozen=True)
class Verdict:
    """Whether a check passed, and the actual and expected values its assert record carries."""

    passed: bool
    actual: JsonValue
    expected: JsonValue


type Verifier = Callable[[object, Args], Verdict]


def _recorded_key(key: object) -> str:
    """*key* spelled the way `json.dumps` spells a dict key."""
    if isinstance(key, str):
        return key
    if key is None or isinstance(key, bool | int | float):
        return json.dumps(key)
    return str(key)


def recorded(value: object) -> JsonValue:
    """*value* as the assert record writes it, which serializes with `default=str`."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list | tuple):
        return [recorded(item) for item in value]
    if isinstance(value, dict):
        return {_recorded_key(key): recorded(item) for key, item in value.items()}
    return str(value)


def verdict(passed: bool, actual: object, expected: object) -> Verdict:
    return Verdict(passed=passed, actual=recorded(actual), expected=recorded(expected))


def json_value(value: object) -> JsonValue:
    """*value* as parsed JSON, refused with `ValueError` on anything JSON cannot hold."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {str(key): json_value(item) for key, item in value.items()}
    raise ValueError(f"not a JSON value: {type(value).__name__}")
