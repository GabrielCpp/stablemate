"""The books of the services that own what this run's book refers to. The first reference to an owner loads
its book and starts a surface for it on the run's own environment; the run's end stops them all. The owner's
book arranges a record a journey needs, and answers about it when a read passes the owner's answer on."""

from __future__ import annotations

import importlib
import json
from typing import TYPE_CHECKING, Any, Callable, cast

from ostler.book.backstage import CannotArrange
from ostler.book.boundary import Needs
from ostler.book.environment import Environment
from ostler.book.errors import BookError
from ostler.book.http import Endpoint, Reply
from ostler.book.journey import StepResult, difference
from ostler.book.model import Model
from ostler.book.state import Axes
from ostler.book.surface import Surface

if TYPE_CHECKING:
    from ostler.book.service import Service

Play = Callable[[object, Model, Surface], StepResult]


def book_of(call: object) -> str:
    """The module name of the book whose endpoints define this call's class."""
    return ".".join(type(call).__module__.split(".")[:2])


def failed(step: object, model: Model, note: str) -> StepResult:
    return StepResult(step, None, None, model.rows(), (), False, note)


class Owners:
    """What this run holds of the owners it met. Class state, like `Landings`: a run is one process."""

    environment: Environment | None = None
    surfaced: Callable[[Service[Any]], Surface] | None = None
    fresh: Callable[[Service[Any], Surface], Model] | None = None
    books: dict[str, tuple[Service[Any], Surface]] = {}
    models: dict[str, Model] = {}
    handed: dict[str, list[object]] = {}
    needs: list[Needs] = []
    loaded: list[str] = []

    @classmethod
    def begin(cls, environment: Environment, surfaced: Callable[[Service[Any]], Surface],
              fresh: Callable[[Service[Any], Surface], Model]) -> None:
        cls.environment, cls.surfaced, cls.fresh = environment, surfaced, fresh
        cls.books, cls.models, cls.handed, cls.needs, cls.loaded = {}, {}, {}, [], []

    @classmethod
    def close(cls) -> None:
        books, cls.books = cls.books, {}
        cls.models, cls.handed = {}, {}
        for _, surface in books.values():
            surface.stop()
        cls.environment = cls.surfaced = cls.fresh = None

    @classmethod
    def journey(cls) -> None:
        """A journey begins: no owner is fresh yet, and no record has been handed over."""
        for needed in cls.needs:
            needed.forget()
        cls.models, cls.handed, cls.needs = {}, {}, []

    @classmethod
    def owner(cls, module: str) -> tuple[Service[Any], Surface]:
        if module in cls.books:
            return cls.books[module]
        if cls.environment is None or cls.surfaced is None:
            raise BookError(f"{module} is an owner, and no run has begun to start its surface")
        try:
            service: Service[Any] = importlib.import_module(f"{module}.service").service
        except Exception as crash:
            raise BookError(f"{module} cannot be loaded as an owner's book: {type(crash).__name__}: {crash}") from None
        cls.lacks(module, service)
        try:
            surface = cls.surfaced(service)
        except BookError as wrong:
            raise BookError(f"{module} cannot be reached in {cls.environment.name}: {wrong}") from None
        surface.start()
        cls.books[module] = (service, surface)
        cls.loaded.append(module)
        return cls.books[module]

    @classmethod
    def lacks(cls, module: str, service: Service[Any]) -> None:
        environment = cls.environment
        assert environment is not None
        own = service.environments.get(environment.name) or service.environments.get(service.default_environment)
        if own is None:
            return
        hosts = [host for host in own.hosts if host not in environment.hosts]
        secrets = [handle for handle in own.secrets if handle not in environment.secrets]
        if hosts or secrets:
            missing = [f"host {h}" for h in hosts] + [f"secret {s}" for s in secrets]
            raise BookError(f"{module} needs {', '.join(missing)}, which environment {environment.name!r} lacks")

    @classmethod
    def arrange(cls, needed: Needs, model: Model, play: Play) -> StepResult:
        """The given taken: the owner's book makes the record in the state, and the journey is handed it."""
        owner, state = needed.foreign.owner, needed.state
        service, surface = cls.owner(owner)
        axes = next((a for a in service.matrices if any(s.name == state for s in a.scenes)), None)
        if axes is None:
            states = ", ".join(dict.fromkeys(s.name for a in service.matrices for s in a.scenes))
            return failed(needed, model, f"{owner} has no state {state!r}; its matrices have {states}")
        if axes.entities is None or axes.state_of is None:
            return failed(needed, model, f"{owner} {state}: the matrix {axes.record!r} says no entity is in a state")
        client = getattr(surface, "client", None)
        ids = getattr(client, "ids", None)
        if ids is None:
            raise BookError(f"{owner} has no HTTP client to read an issued id from: a needed record takes an HTTP owner in this slice")
        owned = cls.models.get(owner)
        if owned is None:
            assert cls.fresh is not None
            owned = cls.models[owner] = cls.fresh(service, surface)
        for step in axes.scene(state).reached_by(owned.today):
            done = play(step, owned, surface)
            if done.skipped:
                raise CannotArrange(done.skipped)
            if not done.ok:
                return failed(needed, model, f"{owner} {state}: {done.text}: {done.note}")
        return cls.hand(needed, model, owner, state, axes, owned, ids)

    @classmethod
    def hand(cls, needed: Needs, model: Model, owner: str, state: str, axes: Axes[Any], owned: Model, ids: Any) -> StepResult:
        taken = cls.handed.setdefault(owner, [])
        assert axes.entities is not None and axes.state_of is not None
        found = [e for e in axes.entities(owned) if axes.state_of(owned, e) == state and e not in taken]
        if len(found) != 1:
            return failed(needed, model, f"{owner} {state}: {len(found)} {axes.record} entities are in the state, one is needed")
        entity = found[0]
        real = ids.real(type(entity), getattr(entity, "id"))
        if real is None:
            return failed(needed, model, f"{owner} {state}: the app issued no id the owner's client knows for {entity}")
        needed.arranged(real, entity)
        taken.append(entity)
        cls.needs.append(needed)
        return StepResult(needed, None, None, model.rows(), (), True)

    @classmethod
    def judge(cls, step: Endpoint) -> str:
        """Why the neighbour's answer to a step that passes the owner's on is not what the book derives from the
        owner's answer, or an empty string."""
        passes = type(step).passes
        if passes is None:
            raise BookError(f"{type(step).__name__} passes nothing on")
        reply = getattr(step, "reply", None)
        if reply is None:
            raise BookError(f"{type(step).__name__} has no answer to judge against the owner's")
        call = passes.asks(step)
        owner = book_of(call)
        _, surface = cls.owner(owner)
        send = cast("Callable[[Endpoint], Reply] | None", getattr(surface, "send", None))
        if not callable(send):
            raise BookError(f"{owner} has no HTTP surface to ask: a read that passes an answer on takes an HTTP owner in this slice")
        call.by = step.by
        asked = send(call)
        if asked.refusal is not None:
            return f"the owner {owner} refused {call}: {asked.refusal}"
        expected = passes.derived(asked.body)
        found = difference(expected, reply.body)
        if not found:
            return ""
        return (f"{type(step).__name__} passes {owner}'s answer on as '{passes.says()}': the owner answered {dump(asked.body)}, "
                f"which derives {dump(expected)}, and the app answered {dump(reply.body)}: {found}")


def dump(body: Any) -> str:
    return json.dumps(body, default=str)
