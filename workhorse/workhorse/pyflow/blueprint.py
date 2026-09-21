"""Blueprints: node libraries a workflow composes, rather than methods it owns."""
from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from types import FunctionType
from typing import Any

from workhorse.pyflow.errors import UnknownNodeError
from workhorse.pyflow.names import NameIndex

NODE_ATTR = "__workhorse_node__"


@dataclass(frozen=True)
class NodeSpec:
    """What registration knows about a node function."""

    fn: Callable[..., Any]
    name: str
    blueprint: str
    aliases: tuple[str, ...] = ()
    retries: int = 0
    returns: Any = None
    dir_names: tuple[str, ...] = field(default=())
    stub: Callable[..., Any] | None = None


def node_spec(fn: Callable[..., Any]) -> NodeSpec:
    """The registration stamped on `fn`, or a loud error naming the fix."""
    spec = getattr(fn, NODE_ATTR, None)
    if spec is None:
        raise UnknownNodeError(
            f"{getattr(fn, '__qualname__', fn)!r} is not a blueprint node — decorate "
            "it with @<blueprint>.node so it gets a name, a span and a recorded "
            "output.json, or call it directly if it is a plain helper"
        )
    return spec


def _return_type(fn: Callable[..., Any]) -> Any:
    """The node's return annotation as a *class*, not the string PEP 563 leaves behind."""
    try:
        annotation = inspect.signature(fn, eval_str=True).return_annotation
    except (TypeError, ValueError, NameError):
        return None
    if annotation is inspect.Signature.empty or isinstance(annotation, str):
        return None
    return annotation


class Blueprint:
    """A named library of node functions."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.index: NameIndex[NodeSpec] = NameIndex("node", owner=f"blueprint {name!r}")

    def node(
        self,
        fn: FunctionType | None = None,
        *,
        aliases: Iterable[str] = (),
        retries: int = 0,
        stub: Callable[..., Any] | None = None,
    ) -> Any:
        """Register a node."""
        alias_tuple = tuple(aliases)

        def decorate(target: FunctionType) -> FunctionType:
            name = target.__name__
            spec = NodeSpec(
                fn=target,
                name=name,
                blueprint=self.name,
                aliases=alias_tuple,
                retries=retries,
                returns=_return_type(target),
                dir_names=(name, *alias_tuple),
                stub=stub,
            )
            self.index.register(name, spec, alias_tuple)
            setattr(target, NODE_ATTR, spec)
            return target

        return decorate if fn is None else decorate(fn)

    def node_names(self) -> list[str]:
        """Live names only — what `dot` and `--dry-run` render."""
        return self.index.live_names()

    def __repr__(self) -> str:
        return f"Blueprint({self.name!r}, {len(self.index.live_names())} nodes)"
