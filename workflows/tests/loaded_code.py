from __future__ import annotations

import dis
import inspect
from collections.abc import Iterator
from types import CodeType
from typing import Any


def _functions(owner: Any) -> Iterator[Any]:
    if inspect.isclass(owner):
        for value in vars(owner).values():
            if isinstance(value, (staticmethod, classmethod)):
                value = value.__func__
            elif isinstance(value, property):
                value = value.fget
            if value is not None and callable(value):
                yield value
    else:
        yield owner


def _walk(code: CodeType) -> Iterator[CodeType]:
    yield code
    for const in code.co_consts:
        if isinstance(const, CodeType):
            yield from _walk(const)


def code_objects(owner: Any) -> Iterator[CodeType]:
    for function in _functions(owner):
        unwrapped = inspect.unwrap(function)
        code = getattr(unwrapped, "__code__", None)
        if isinstance(code, CodeType):
            yield from _walk(code)


def _flatten(const: object) -> Iterator[str]:
    if isinstance(const, str):
        yield const
    elif isinstance(const, (tuple, frozenset)):
        for item in const:  # pyright: ignore[reportUnknownVariableType]
            yield from _flatten(item)


def strings(owner: Any) -> set[str]:
    return {text for code in code_objects(owner) for const in code.co_consts for text in _flatten(const)}


def names(owner: Any) -> set[str]:
    return {name for code in code_objects(owner) for name in code.co_names}


def stored_attributes(owner: Any) -> set[str]:
    return {
        str(instruction.argval)
        for code in code_objects(owner)
        for instruction in dis.get_instructions(code)
        if instruction.opname == "STORE_ATTR"
    }
