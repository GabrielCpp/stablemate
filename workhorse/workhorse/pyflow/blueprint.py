"""Blueprints: node libraries a workflow composes, rather than methods it owns.

A node is a free function taking `logger` first — the contract today's `scripts/*.py`
already have via `main(logger)`, so they port with the argv/JSON envelope stripped and
nothing else. `add_blueprints(...)` is plural because the point is composition: a
workflow picks up the shared `await_operator` / `commit_all` / `push_branch` rather than
re-implementing them a fourth time.

Nodes return plain typed values. Wrapping them would put `.result[...]` at every
callsite and re-erase the typing that `Concatenate[Logger, P]` just bought.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from types import FunctionType
from typing import Any

from workhorse.pyflow.errors import UnknownNodeError
from workhorse.pyflow.names import NameIndex

# Attribute stamped on a decorated function. `self.call(fn, ...)` takes the function
# object, not a name, so the registration has to travel with the function.
NODE_ATTR = "__workhorse_node__"


@dataclass(frozen=True)
class NodeSpec:
    """What registration knows about a node function."""

    fn: Callable[..., Any]
    name: str
    blueprint: str
    aliases: tuple[str, ...] = ()
    #: Re-calls on exception before the failure propagates. 0 = call once.
    retries: int = 0
    #: The function's return annotation, when it is a class — used to re-validate a
    #: recorded `output.json` back into a typed value for `self.output(node)`.
    returns: Any = None
    #: All names this node's artifacts may live under, live name first. `self.output`
    #: walks these so renaming a node does not orphan a run dir mid-week.
    dir_names: tuple[str, ...] = field(default=())
    #: What `--dry-run` runs in place of `fn` — the author's answer to "what would
    #: this have returned". Same signature as the node. None = a blank return model,
    #: which type-checks and is honest about knowing nothing.
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
    """The node's return annotation as a *class*, not the string PEP 563 leaves behind.

    Every module in this tree carries `from __future__ import annotations`, so a plain
    `inspect.signature` hands back `"Manifest"` rather than `Manifest` — and a string is
    not a model, so `self.output(node)` would quietly return the raw dict instead of the
    typed value the node declared. `eval_str=True` resolves it against the node's own
    module; an annotation that will not resolve (a `TYPE_CHECKING`-only import) degrades
    to untyped rather than failing the decorator, because a run must not hinge on it.
    """
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
        """Register a node. Usable bare (`@bp.node`) or called (`@bp.node(retries=2)`).

        `aliases` are the names this node used to have. They matter as much here as
        on a state: `self.output(node)` resolves by node name against the run
        directory, so renaming a node breaks output lookups in exactly the way
        renaming a state breaks checkpoints.

        `stub` is what a dry run calls instead — `stub=lambda logger, **kw: Report(ok=True)`.
        Declaring one is how a workflow turns `--dry-run` from "every branch takes an
        arbitrary path" into a real smoke test of its happy path; without one the node
        yields a blank instance of its return model.

        There is deliberately no `timeout=`: a node runs in the engine's own process
        and there is no portable way to interrupt it, so the knob would be accepted
        and ignored. The run-wide `WORKHORSE_MAX_RUNTIME_S` budget is what bounds a
        slow node today.
        """
        alias_tuple = tuple(aliases)

        # A `def`, not any callable: a node's *name* is its function name — it keys the
        # index, the run directory and `self.output(node)` — and only a function carries
        # one. A partial or a callable object would register as nameless.
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
