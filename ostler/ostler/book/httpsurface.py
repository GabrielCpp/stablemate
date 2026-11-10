"""The generic surface of an HTTP service: every step is an endpoint call sent
as declared, and after it the service's watch reads are taken and compared whole.
A book's surface keeps only what is specific to its app."""

from __future__ import annotations

from typing import Any, cast

from ostler.book.errors import BookError
from ostler.book.http import Answer, Client, Endpoint, List, Reply, Witness, canonical
from ostler.book.model import Model
from ostler.book.outcome import Done, Outcome


class HttpSurface:
    name = "api"

    def __init__(self, client: Client):
        self.client = client
        self.watch: tuple[Endpoint, ...] = ()

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
        return call.send(self.client)

    def perform(self, step: Any) -> Outcome:
        call = cast(Endpoint, step)
        reply = self.send(call)
        if reply.refusal:
            return reply.refusal
        answer = reply.answer
        self.learn(call, reply)
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
