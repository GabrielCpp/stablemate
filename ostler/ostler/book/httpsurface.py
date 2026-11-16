"""The generic surface of an HTTP service: every step is an endpoint call sent
as declared, and after it the service's watch reads are taken and compared whole.
A book's surface keeps only what is specific to its app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, cast

from ostler.book.errors import BookError
from ostler.book.http import Answer, Client, Endpoint, List, Reply, Witness, breaches, canonical
from ostler.book.model import Model
from ostler.book.outcome import Done, Outcome


@dataclass(frozen=True, eq=False)
class Breach:
    """A rule a list of one app answer broke: the call that read it, the path of the list in the answer and what broke."""

    call: Endpoint
    path: str
    rule: Callable[[list[Any]], list[str]]
    said: str


class HttpSurface:
    name = "api"

    def __init__(self, client: Client):
        self.client = client
        self.watch: tuple[Endpoint, ...] = ()
        self.breached: dict[tuple[int, str, int, str], Breach] = {}
        self.covering: Callable[[Endpoint], tuple[Callable[[list[Any]], list[str]], ...]] | None = None

    def cover(self, covering: Callable[[Endpoint], tuple[Callable[[list[Any]], list[str]], ...]] | None) -> None:
        """What the step in hand lets the run leave out of an answer: for each call, the rules a known defect covers."""
        self.covering = covering

    def judge(self, call: Endpoint, reply: Reply) -> None:
        """The entry rules of every list the answer holds, judged on the entries the app answered."""
        answer = reply.answer
        if answer.body is None:
            return
        for path, rule, said in breaches(answer.body, reply.whole):
            self.breached.setdefault((id(call), path, id(rule), said), Breach(call, path, rule, said))

    def take_breaches(self) -> list[Breach]:
        taken = list(self.breached.values())
        self.breached = {}
        return taken

    def follow(self, watch: tuple[Endpoint, ...]) -> None:
        self.watch = watch

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def restore(self) -> None:
        """Give the next cell a world of its own: fresh accounts and the records the
        model starts with, never by deleting what an earlier cell made."""
        raise NotImplementedError

    def reset(self) -> None:
        self.restore()
        self.client.forget()

    def witnesses(self) -> list[Witness]:
        return [self.client.witness]

    def learn(self, call: Endpoint, reply: Any) -> None:
        """Hook for ids the app issued that the endpoint's `creates` does not name."""

    def send(self, call: Endpoint) -> Reply:
        """Every request the surface makes, a step or a watch read, goes through here."""
        return call.send(self.client, self.covering(call) if self.covering is not None else ())

    def perform(self, step: Any) -> Outcome:
        call = cast(Endpoint, step)
        reply = self.send(call)
        if reply.refusal:
            return reply.refusal
        answer = reply.answer
        self.learn(call, reply)
        self.judge(call, reply)
        view: tuple[object, ...] = ()
        if answer.body is not None:
            found = canonical(answer.body, reply.body, app=True, ids=self.client.ids, where=type(call).__name__)
            view = found if isinstance(answer.body, List) else (found,)
        return Done(self.rows(), view)

    def rows(self) -> tuple[object, ...]:
        out: list[object] = []
        for read in self.watch:
            reply = self.send(read)
            if reply.refusal:
                return ()
            answer = reply.answer
            self.judge(read, reply)
            found = canonical(answer.body, reply.body, app=True, ids=self.client.ids, where=type(read).__name__)
            out.extend(found if isinstance(answer.body, List) else [found])
        return tuple(out)

    def express(self, request: Any, outcome: Done) -> tuple[object, ...]:
        """The answer the model says this call gets, in the form the app's is compared in."""
        call = type(request)
        answer = getattr(request, "reply", None) and request.reply.answer
        if answer is None or answer.body is None:
            answer = call.success()
        if answer is None or answer.body is None:
            return ()
        return self.canon(call.__name__, answer.body, outcome.view or ())

    def canon(self, where: str, shape: Any, view: tuple[object, ...]) -> tuple[object, ...]:
        if isinstance(shape, List):
            return canonical(shape, list(view), app=False, ids=None, where=where)
        if len(view) != 1:
            raise BookError(f"{where}: the answer is one {shape.describe()} but the model's view holds {len(view)}")
        return (canonical(shape, view[0], app=False, ids=None, where=where),)

    def watched(self, model: Model) -> tuple[object, ...]:
        """What the watch reads would list, according to the model."""
        out: list[object] = []
        for read in self.watch:
            outcome = model.copy().perform(read)
            if not isinstance(outcome, Done):
                return ()
            answer = read.success()
            if answer is not None and answer.body is not None:
                out.extend(self.canon(type(read).__name__, answer.body, outcome.view or ()))
        return tuple(out)

    def shown(self, row: object) -> object:
        """The row as the first watch read that can show it lists it."""
        problems: list[str] = []
        for read in self.watch:
            shape = cast(Answer, read.success()).body
            item = shape.of if isinstance(shape, List) else shape
            try:
                return canonical(item, row, app=False, ids=None, where=type(read).__name__)
            except BookError as wrong:
                problems.append(str(wrong))
        raise BookError("no watch read can show " + repr(row) + ": " + "; ".join(problems))
