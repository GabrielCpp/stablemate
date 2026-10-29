"""Rendering: one Document walked into the markdown reference of every setting it declares."""

from __future__ import annotations

import json
import types
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Union, cast, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from .base import Section

PLACEHOLDER = "<name>"

_SCALARS: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    Any: "any value",
}


@dataclass(frozen=True)
class ReferenceRow:
    """One setting as the reference prints it."""

    path: str
    type: str
    default: str
    description: str
    examples: tuple[str, ...]
    env: str
    precedence: str
    legacy: str


def _is_section(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, BaseModel)


def _members(tp: Any) -> list[Any]:
    return [arg for arg in get_args(tp) if arg is not type(None)]


def _unwrapped(tp: Any) -> Any:
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        members = _members(tp)
        if len(members) == 1:
            return _unwrapped(members[0])
    return tp


def _label(tp: Any) -> str:
    tp = _unwrapped(tp)
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        return " or ".join(_label(arg) for arg in _members(tp))
    if origin is Literal:
        return " | ".join(json.dumps(arg) for arg in get_args(tp))
    if origin is list:
        return f"list of {_label(get_args(tp)[0])}"
    if origin is dict:
        value = get_args(tp)[1]
        return "table of tables" if _is_section(_unwrapped(value)) else f"table of {_label(value)}"
    if _is_section(tp):
        return "table"
    return _SCALARS.get(tp, getattr(tp, "__name__", str(tp)))


def yaml_value(value: Any) -> str:
    """A value as it reads in a YAML file, inline."""
    return json.dumps(value, ensure_ascii=False, default=str)


def toml_value(value: Any) -> str:
    """A value as it reads in a TOML file, inline."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        pairs = (f"{json.dumps(key) if not str(key).isidentifier() else key} = {toml_value(item)}" for key, item in value.items())
        return "{ " + ", ".join(pairs) + " }"
    return json.dumps(value, default=str)


def _default_text(info: FieldInfo, extra: dict[str, Any], render: Callable[[Any], str]) -> str:
    if extra.get("default"):
        return str(extra["default"])
    if info.default_factory is not None:
        produced = cast("Callable[[], Any]", info.default_factory)()
        return "empty" if not produced else render(produced)
    if info.default is PydanticUndefined:
        return "required"
    if info.default is None:
        return "unset"
    return render(info.default)


def _extra(info: FieldInfo) -> dict[str, Any]:
    raw = info.json_schema_extra
    return {str(key): value for key, value in raw.items()} if isinstance(raw, dict) else {}


def _row(path: str, info: FieldInfo, label: str, render: Callable[[Any], str]) -> ReferenceRow:
    extra = _extra(info)
    return ReferenceRow(
        path=path,
        type=str(extra.get("type") or label),
        default=_default_text(info, extra, render),
        description=info.description or "",
        examples=tuple(render(example) for example in info.examples or []),
        env=str(extra.get("env", "")),
        precedence=str(extra.get("precedence", "")),
        legacy=str(extra.get("legacy", "")),
    )


def _child_section(tp: Any) -> tuple[type[BaseModel], str] | None:
    tp = _unwrapped(tp)
    if _is_section(tp):
        return tp, "."
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        for member in _members(tp):
            if _is_section(member):
                return member, "."
    if origin is list:
        inner = _unwrapped(get_args(tp)[0])
        if _is_section(inner):
            return inner, "[]."
    if origin is dict:
        inner = _unwrapped(get_args(tp)[1])
        if _is_section(inner):
            return inner, f".{PLACEHOLDER}."
        if get_origin(inner) is list:
            deeper = _unwrapped(get_args(inner)[0])
            if _is_section(deeper):
                return deeper, f".{PLACEHOLDER}[]."
    return None


def reference_rows(
    model: type[BaseModel], prefix: str = "", render: Callable[[Any], str] = toml_value
) -> list[ReferenceRow]:
    """Every setting ``model`` declares, depth first, each table before its members."""
    rows: list[ReferenceRow] = []
    for name, info in model.model_fields.items():
        path = f"{prefix}{name}"
        rows.append(_row(path, info, _label(info.annotation), render))
        child = _child_section(info.annotation)
        if child is not None:
            section, joiner = child
            rows.extend(reference_rows(section, f"{path}{joiner}", render))
    return rows


def _render_row(row: ReferenceRow) -> list[str]:
    lines = [f"### `{row.path}`", "", row.description, ""]
    lines.append(f"- type: `{row.type}`")
    lines.append(f"- default: {row.default}")
    if row.env:
        lines.append(f"- env: `${row.env}`")
    if row.precedence:
        lines.append(f"- precedence: {row.precedence}")
    if row.legacy:
        lines.append(f"- legacy: {row.legacy}")
    lines.extend(f"- example: `{example}`" for example in row.examples)
    lines.append("")
    return lines


def render_reference(
    model: type[Section],
    *,
    title: str,
    intro: str = "",
    render: Callable[[Any], str] = toml_value,
) -> str:
    """The markdown reference of ``model``: every setting with its type, default, meaning, example, environment variable and legacy alias."""
    lines = [f"# {title}", ""]
    if intro:
        lines.extend([intro, ""])
    for row in reference_rows(model, render=render):
        lines.extend(_render_row(row))
    return "\n".join(lines).rstrip("\n") + "\n"
