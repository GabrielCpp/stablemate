"""The three ways a state can end, and nothing else."""
from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any, Generic, ParamSpec, Self, TypeAlias

P = ParamSpec("P")


class _Because:
    """The reason a transition was taken, chained on after the constructor."""

    __slots__ = ("reason",)

    def __init__(self) -> None:
        self.reason = ""

    def because(self, reason: str) -> Self:
        """Say in one sentence why this transition was taken."""
        self.reason = reason
        return self

    def _why(self) -> str:
        return f", because={self.reason!r}" if self.reason else ""


def state_name(target: Callable[..., Any]) -> str:
    """The name a transition target checkpoints under: the plain method name."""
    name = getattr(target, "__name__", None)
    if not name:
        raise TypeError(
            f"transition target {target!r} has no __name__ — a transition must name "
            "a state method (e.g. `self.qa`), not a lambda or a partial"
        )
    return name


def bind_params(
    target: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    """Validate the transition's arguments against the next state's own signature, and flatten them to the `{name: value}` dict the checkpoint stores."""
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"transition target {target!r} has no inspectable signature") from exc

    for parameter in signature.parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            raise TypeError(
                f"state '{state_name(target)}' declares {parameter} — a state's "
                "parameters ARE its checkpoint, so *args/**kwargs cannot be named "
                "on disk; declare them explicitly"
            )

    try:
        bound = signature.bind(*args, **kwargs)
    except TypeError as exc:
        raise TypeError(
            f"transition to '{state_name(target)}' does not match its signature "
            f"{signature}: {exc}"
        ) from exc
    return dict(bound.arguments)


class Continue(_Because, Generic[P]):
    """Hand `result` back and step to `next` with these parameters."""

    __slots__ = ("result", "target", "state", "params")

    def __init__(
        self,
        result: object,
        next: Callable[P, "Transition"],  # noqa: A002 — the spec's name; reads as prose
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__()
        self.result = result
        self.target = next
        self.state = state_name(next)
        self.params = bind_params(next, args, kwargs)

    def __repr__(self) -> str:
        return f"Continue(→{self.state}, {self.params!r}{self._why()})"


class Done(_Because):
    """The run is over; `result` is what it produced."""

    __slots__ = ("result",)

    def __init__(self, result: object = None) -> None:
        super().__init__()
        self.result = result

    def __repr__(self) -> str:
        return f"Done({self.result!r}{self._why()})"


class Await(_Because, Generic[P]):
    """Checkpoint here; resume at `next` with these parameters when `path` changes."""

    __slots__ = ("path", "questions", "target", "state", "params", "kind")

    def __init__(
        self,
        path: str | Path,
        questions: str,
        next: Callable[P, "Transition"],  # noqa: A002 — see Continue
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__()
        self.path = Path(path)
        self.questions = questions
        self.target = next
        self.state = state_name(next)
        self.params = bind_params(next, args, kwargs)
        self.kind = "operator"

    @classmethod
    def on_machine(
        cls,
        path: str | Path,
        questions: str,
        next: Callable[P, "Transition"],  # noqa: A002 — see Continue
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> "Await[P]":
        """An `Await` whose answer a running process owes, not a person."""
        await_ = cls(path, questions, next, *args, **kwargs)
        await_.kind = "machine"
        return await_

    def __repr__(self) -> str:
        return f"Await({self.path}, {self.kind}, →{self.state}, {self.params!r}{self._why()})"


Transition: TypeAlias = "Continue[...] | Done | Await[...]"
