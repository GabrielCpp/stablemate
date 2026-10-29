"""Declaration: the base every table shares and the field helper that carries a setting's documentation."""

from __future__ import annotations

import difflib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import PydanticUndefined


class Section(BaseModel):
    """A table of settings. A key it does not declare is kept and reported, never refused."""

    model_config = ConfigDict(extra="allow")


class FreeSection(Section):
    """A table whose undeclared keys belong to someone outside the tools, so none is ever reported as stray."""


def setting(
    default: Any = PydanticUndefined,
    *,
    description: str,
    examples: list[Any],
    env: str = "",
    precedence: str = "",
    legacy: str = "",
    default_text: str = "",
    type_text: str = "",
    key: str = "",
    factory: Callable[[], Any] | None = None,
) -> Any:
    """One setting: its default and the documentation the reference prints."""
    extra: dict[str, Any] = {
        name: value
        for name, value in (
            ("env", env),
            ("precedence", precedence),
            ("legacy", legacy),
            ("default", default_text),
            ("type", type_text),
            ("key", key),
        )
        if value
    }
    if factory is not None:
        return Field(
            default_factory=factory,
            description=description,
            examples=examples,
            json_schema_extra=extra,
        )
    return Field(default, description=description, examples=examples, json_schema_extra=extra)


@dataclass(frozen=True)
class StrayKey:
    """A key the Document does not declare, and the declared key it most resembles."""

    path: str
    closest: str


def _walk(value: Any, prefix: str, found: list[StrayKey]) -> None:
    if isinstance(value, Section):
        declared = list(type(value).model_fields)
        for key in {} if isinstance(value, FreeSection) else value.model_extra or {}:
            near = difflib.get_close_matches(key, declared, n=1)
            found.append(StrayKey(f"{prefix}{key}", f"{prefix}{near[0]}" if near else ""))
        for name in declared:
            _walk(getattr(value, name), f"{prefix}{name}.", found)
    elif isinstance(value, dict):
        for name, item in cast("dict[str, Any]", value).items():
            _walk(item, f"{prefix}{name}.", found)
    elif isinstance(value, list):
        for index, item in enumerate(cast("list[Any]", value)):
            _walk(item, f"{prefix}{index}.", found)


def stray_keys(document: Section) -> list[StrayKey]:
    """Every key under ``document`` that no table declares, with the closest declared key."""
    found: list[StrayKey] = []
    _walk(document, "", found)
    return found
