"""The books of the services that own what this run's book refers to. The first reference to an owner loads
its book and starts a surface for it on the run's own environment; the run's end stops them all. The owner's
book arranges a record a journey needs, and answers about it when a read passes the owner's answer on."""

from __future__ import annotations

import importlib
import json
from typing import TYPE_CHECKING, Any, Callable, cast

from ostler.book.backstage import CannotArrange
from ostler.book.boundary import Needs
from ostler.book.domain import Fixture
from ostler.book.environment import Environment
from ostler.book.errors import BookError
from ostler.book.http import Endpoint, Reply
from ostler.book.journey import StepResult, difference
from ostler.book.model import Model
from ostler.book.outcome import Done, Refusal
from ostler.book.state import Axes
from ostler.book.status import Status, refused as turned_away
from ostler.book.surface import Surface

if TYPE_CHECKING:
    from ostler.book.service import Service

Play = Callable[[object, Model, Surface], StepResult]
Listing = Callable[[Surface, Model], tuple[object, ...]]


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
        named = [a for a in service.matrices if any(sc.name == state for sc in a.scenes)]
        if not named:
            states = ", ".join(dict.fromkeys(sc.name for a in service.matrices for sc in a.scenes))
            return failed(needed, model, f"{owner} has no state {state!r}; its matrices have {states}")
        axes = cls.matrix_of(service, needed.foreign.record, state, named)
        if axes is None:
            names = ", ".join(a.record for a in named)
            return failed(needed, model, f"{owner} {state}: no matrix of {names} makes a {needed.foreign.record.__name__} in that state")
        if axes.entities is None or axes.state_of is None:
            return failed(needed, model, f"{owner} {state}: the matrix {axes.record!r} says no entity is in a state")
        client = getattr(surface, "client", None)
        ids = getattr(client, "ids", None)
        if ids is None:
            raise BookError(f"{owner}'s surface keeps no client with the ids the app issued, which a needed record is handed")
        owned = cls.model_of(owner, service, surface)
        for step in axes.scene(state).reached_by(owned.today):
            done = play(step, owned, surface)
            if done.skipped:
                raise CannotArrange(done.skipped)
            if not done.ok:
                return failed(needed, model, f"{owner} {state}: {done.text}: {done.note}")
        return cls.hand(needed, model, owner, state, axes, owned, ids)

    @classmethod
    def matrix_of(cls, service: Service[Any], record: type, state: str, named: list[Axes[Any]]) -> Axes[Any] | None:
        """The first matrix whose scene `state`, arranged on a fresh model alone, leaves an entity of `record` in
        that state."""
        for axes in named:
            if axes.entities is None or axes.state_of is None:
                continue
            try:
                twin = axes.scene(state).arrange(service.new_model(axes.today))
                if any(isinstance(e, record) and axes.state_of(twin, e) == state for e in axes.entities(twin)):
                    return axes
            except Exception:
                continue
        return None

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
    def model_of(cls, owner: str, service: Service[Any], surface: Surface) -> Model:
        owned = cls.models.get(owner)
        if owned is None:
            assert cls.fresh is not None
            owned = cls.models[owner] = cls.fresh(service, surface)
        return owned

    @classmethod
    def asked(cls, call: object) -> tuple[str, Service[Any], Surface]:
        """The owner a call of a neighbour's book names, its book and its surface. The call must be one of the
        endpoints that book declares."""
        owner = book_of(call)
        service, surface = cls.owner(owner)
        if type(call) not in service.endpoints:
            raise BookError(f"{type(call).__name__} is no endpoint of {owner}: a call a book passes on or reaches is one of the owner's endpoints")
        return owner, service, surface

    @classmethod
    def sender(cls, owner: str, surface: Surface, what: str) -> Callable[[Endpoint], Reply]:
        send = cast("Callable[[Endpoint], Reply] | None", getattr(surface, "send", None))
        if not callable(send):
            raise BookError(f"{owner}'s surface cannot send one call and return its reply, which {what} needs")
        return send

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
        owner, _, surface = cls.asked(call)
        send = cls.sender(owner, surface, "a read that passes an answer on")
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

    @classmethod
    def refused(cls, step: Endpoint, app: Status) -> str:
        """Why the owner's refusal of the call `step` passes on or reaches, and the `app` status the neighbour
        answered, are not what the book's map says, or an empty string."""
        kind = type(step)
        if kind.passes is not None:
            call, claim = kind.passes.asks(step), kind.passes
        elif kind.reaches is not None:
            call, claim = kind.reaches.call(step), kind.reaches
        else:
            raise BookError(f"{kind.__name__} passes nothing on and reaches nothing: claim its own refusals with Refused")
        owner, _, surface = cls.asked(call)
        send = cls.sender(owner, surface, "a claim that the owner refuses")
        call.by = step.by
        asked = send(call)
        if asked.refusal is None:
            return f"{kind.__name__} claims the owner {owner} refuses {call}, and the owner answered {asked.status} and did not refuse"
        if not turned_away(app):
            return (f"{kind.__name__} claims the owner {owner} refuses {call}: the owner refused with {asked.status} "
                    f"and the app answered {app} and did not refuse")
        if asked.status not in claim.refused:
            held = ", ".join(str(k) for k in claim.refused) or "none"
            return (f"{kind.__name__}: the owner {owner} refused {call} with {asked.status} and the map names no such status: "
                    f"it holds {held}")
        mapped = claim.refused[asked.status]
        if mapped != app:
            return (f"{kind.__name__}: the owner {owner} refused {call} with {asked.status}, the book maps it to {mapped}, "
                    f"and the app answered {app}")
        return ""

    @classmethod
    def prepare(cls, step: Endpoint) -> None:
        """A step that reaches the owner's call is about to be sent: the owner has a model before the app moves."""
        reaches = type(step).reaches
        assert reaches is not None
        owner, service, surface = cls.asked(reaches.call(step))
        cls.model_of(owner, service, surface)

    @classmethod
    def reach(cls, step: Endpoint, listing: Listing) -> str:
        """Why the owner's app, after the neighbour answered a step that reaches the owner's call, does not hold
        what the owner's book expects of that call, or an empty string."""
        reaches = type(step).reaches
        if reaches is None:
            raise BookError(f"{type(step).__name__} reaches nothing")
        call = reaches.call(step)
        owner, service, surface = cls.asked(call)
        action = type(call).carries
        if action is None:
            raise BookError(f"{type(call).__name__} carries no action on {owner}'s model: a read is nothing for a write to reach")
        call.by = step.by
        owned = cls.model_of(owner, service, surface)
        outcome = owned.perform(cls.modelled(call, action))
        where = f"{type(step).__name__} reaches {call}"
        if isinstance(outcome, Refusal):
            return (f"{where}: the owner's book expects a refusal there ({outcome}), and the app answered the step: "
                    "claim the refusal with OwnerRefused")
        if not isinstance(outcome, Done):
            return f"{where}: the owner's book says {outcome}"
        expected, found = listing(surface, owned), surface.rows()
        if expected == found:
            return ""
        return (f"{where}: {owner}'s app holds {[str(r) for r in found]} where the owner's book expects "
                f"{[str(r) for r in expected]}")

    @classmethod
    def modelled(cls, call: Endpoint, action: type) -> Endpoint:
        """The call as the owner's model takes it: a needed record is the model's own entity, not the id the
        owner's app issued. The record is the path's, or the request message's where the call has no path."""
        if isinstance(call.of, Needs):
            return call.varied(of=cls.entity(call.of, action))
        if isinstance(call.body_value, Needs):
            return call.varied(body=cls.entity(call.body_value, action))
        return call

    @classmethod
    def entity(cls, needed: Needs, action: type) -> object:
        entity = needed.record
        accepts = getattr(action, "accept", None)
        if isinstance(accepts, type) and issubclass(accepts, Fixture) and not isinstance(entity, accepts):
            entity = accepts.of(entity)
        return entity


def dump(body: Any) -> str:
    return json.dumps(body, default=str)
