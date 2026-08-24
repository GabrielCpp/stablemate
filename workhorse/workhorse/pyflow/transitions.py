"""The three ways a state can end, and nothing else.

`Continue(result, next, **params)` / `Done(result)` / `Await(path, questions, next,
**params)` make illegal states unrepresentable — `WorkflowState(result=..., next=None)`
leaves "what does `result` mean while continuing?" undefined and unenforceable. Failure
is not a fourth arm: it is `raise WorkflowFailed(reason)`, which needs a traceback.

`Await` differs from `Continue` in exactly one line of the driver, which is the point:
the transition is recorded identically and the wait is something the driver does
between recording it and stepping.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any, Generic, ParamSpec, TypeAlias

P = ParamSpec("P")


def state_name(target: Callable[..., Any]) -> str:
    """The name a transition target checkpoints under: the plain method name.

    Identity is the plain name (and a rename declares an alias) — pinning every
    state with an explicit identifier would tax all states forever to protect
    against a rare event.
    """
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
    """Validate the transition's arguments against the next state's own signature,
    and flatten them to the `{name: value}` dict the checkpoint stores.

    This is the second of the three moments arguments are checked: `ParamSpec` covers
    author time in the editor, this covers transition time at runtime, and coercion
    against the signature covers resume time. It exists because a checkpoint is only
    hand-editable if its params are named, so `Continue(x, self.qa, "login")` has to
    become `{"story": "login"}` before it reaches disk.
    """
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError) as exc:  # builtins, C callables
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


class Continue(Generic[P]):
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
        self.result = result
        self.target = next
        self.state = state_name(next)
        self.params = bind_params(next, args, kwargs)

    def __repr__(self) -> str:
        return f"Continue(→{self.state}, {self.params!r})"


class Done:
    """The run is over; `result` is what it produced."""

    __slots__ = ("result",)

    def __init__(self, result: object = None) -> None:
        self.result = result

    def __repr__(self) -> str:
        return f"Done({self.result!r})"


class Await(Generic[P]):
    """Checkpoint here; resume at `next` with these parameters when `path` changes.

    `questions` is the ask written to `path` for whoever is being waited on (empty
    to wait on a file this workflow does not write). The checkpoint — including
    `waiting_on` — is written *before* the wait begins, so "blocked on a human at
    docs/epics/auth/context.md" is on disk and readable whether or not the process
    survives.

    Because resume re-enters a state from the top with no intra-state memo,
    an `Await`'s target must be a state whose prefix is cheap: the natural shape is
    a state that exists only to consume the answer and reads everything else by
    reference via `self.output(...)`.

    `kind` says **who owes the answer**, and it is the difference between a page and
    a wait. The default `operator` is the gate this class was written for: nothing is
    running for the run, and nothing will until a human writes in the file — so groom
    fires BLOCKED when it opens and WAITING while it stays open, because a person not
    knowing they are the bottleneck is the one condition an alert can shorten. A
    `machine` wait is the opposite fact wearing the same shape: a detached job is
    running right now and will touch the file itself when it finishes, so a page
    shortens nothing and the alert text — "nothing is running for it" — is simply
    false. Build one with :meth:`on_machine`; groom already exempts every non-operator
    wait, the way it exempts a cap wait.
    """

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
        """An `Await` whose answer a running process owes, not a person.

        A classmethod rather than a `kind=` keyword because the trailing `**kwargs`
        *are* the next state's parameters: a keyword here would shadow any state that
        happened to take one called `kind`, and silently, at the one callsite that
        needed it most.
        """
        await_ = cls(path, questions, next, *args, **kwargs)
        await_.kind = "machine"
        return await_

    def __repr__(self) -> str:
        return f"Await({self.path}, {self.kind}, →{self.state}, {self.params!r})"


# `[...]` and not `[Any]`: both classes are generic over a *ParamSpec*, and the gradual
# form of one is `...` — the next state's parameter list, whatever it is. Spelled `Any`,
# the alias reads as "a next state taking one positional argument", so a state returning
# `Continue(None, self.settle, diagnostics=[...])` does not satisfy its own `-> Transition`.
Transition: TypeAlias = "Continue[...] | Done | Await[...]"
