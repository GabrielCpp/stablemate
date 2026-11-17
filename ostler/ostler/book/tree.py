"""A shape that holds itself.

An `Object` is built from values, so it cannot name itself in its own fields. A field holds `Itself(name)` instead,
and the object of that name replaces the placeholder when it is built, which makes the shape graph a real cycle.
These helpers resolve the placeholders, re-point a copy of an object at itself, and report any placeholder left.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import ostler.book.http as http

__all__ = ["bind", "repoint", "unresolved"]


def bind(root: http.Object) -> None:
    """Replaces every `Itself` naming `root` inside it with `root`, and any other shape it reaches on the way."""
    done = {id(root)}

    def resolved(shape: Any) -> Any:
        if isinstance(shape, http.Itself):
            return root if shape.name == root.name else shape
        if isinstance(shape, http.Object):
            if id(shape) not in done:
                done.add(id(shape))
                fill(shape)
            return shape
        if isinstance(shape, (http.List, http.Map)):
            held = resolved(shape.of)
            return shape if held is shape.of else dataclasses.replace(shape, of=held)
        return shape

    def fill(target: http.Object) -> None:
        for key, spec in list(target.fields.items()):
            held = resolved(spec.shape)
            if held is not spec.shape:
                target.fields[key] = dataclasses.replace(spec, shape=held)

    fill(root)


def _reaches(shape: Any, old: http.Object, seen: set[int]) -> bool:
    if shape is old:
        return True
    if isinstance(shape, (http.List, http.Map)):
        return _reaches(shape.of, old, seen)
    if isinstance(shape, http.Object) and id(shape) not in seen:
        seen.add(id(shape))
        return any(_reaches(spec.shape, old, seen) for spec in shape.fields.values())
    return False


def repoint(copy: http.Object, old: http.Object) -> http.Object:
    """Makes every reference to `old` inside `copy` a reference to `copy`. An object that reaches `old` is copied on the way, so `old`
    and what it holds stay as they were."""
    cloned: dict[int, http.Object] = {}

    def swapped(shape: Any) -> Any:
        if shape is old:
            return copy
        if isinstance(shape, (http.List, http.Map)):
            held = swapped(shape.of)
            return shape if held is shape.of else dataclasses.replace(shape, of=held)
        if isinstance(shape, http.Object):
            if id(shape) in cloned:
                return cloned[id(shape)]
            if not _reaches(shape, old, set()):
                return shape
            twin = http.Object(shape.name)
            twin.one_ofs, twin.togethers = shape.one_ofs, shape.togethers
            cloned[id(shape)] = twin
            twin.fields = {k: dataclasses.replace(s, shape=swapped(s.shape)) for k, s in shape.fields.items()}
            return twin
        return shape

    copy.fields = {k: dataclasses.replace(s, shape=swapped(s.shape)) for k, s in copy.fields.items()}
    return copy


def unresolved(shape: Any, where: str, seen: set[int] | None = None) -> list[str]:
    """Each `Itself` left in a shape, with the path of the field that holds it."""
    seen = seen if seen is not None else set()
    if isinstance(shape, http.Itself):
        return [f"{where}: {shape.refusal()}"]
    if isinstance(shape, (http.List, http.Map)):
        return unresolved(shape.of, where + ("[]" if isinstance(shape, http.List) else "{}"), seen)
    if isinstance(shape, http.Object) and id(shape) not in seen:
        seen.add(id(shape))
        return [line for name, spec in shape.fields.items() for line in unresolved(spec.shape, f"{where}.{name}", seen)]
    return []
