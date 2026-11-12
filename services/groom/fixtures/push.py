"""A workflow run as it reports to groom. `Push` is what one push carries; the
factories fill one thing in and pass the rest through. A run's name is minted from
a counter, so every call of a factory is a run no earlier cell used."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count
from typing import Any, Iterable

from ostler.book import Actor, Fixture

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
_counter = count()


def _next_name() -> str:
    n = next(_counter)
    return "r" + _ALPHABET[(n // 36) % 36] + _ALPHABET[n % 36]


@dataclass(eq=False)
class Push(Fixture):
    container_id: str | None = None
    name: str | None = None
    repo_name: str | None = None
    repo_branch: str | None = None
    current_node: str | None = None
    file_path: str | None = None
    question: str | None = None
    exit_code: int | None = None

    def __str__(self) -> str:
        return self.name or self.container_id or "(no run)"

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Push]:
        full = dict(current_node="plan", file_path="gates/approve.md", question="Ship it?", exit_code=1)
        aimed = tuple(cls.of(run).but(**full) for run in state.runs)
        return (running(**full), *aimed)


@dataclass(eq=False)
class Query(Fixture):
    q: str | None = None

    def __str__(self) -> str:
        return f"filter {self.q}" if self.q else "everything"

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Query]:
        return (Query(), *(Query(q=run.name) for run in state.runs), Query(q=_next_name()))


@dataclass(eq=False)
class Settings(Fixture):
    enabled: bool | None = None

    def __str__(self) -> str:
        return "attendant on" if self.enabled else "attendant off"

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Settings]:
        return (Settings(enabled=True), Settings(enabled=False))


def running(**fields: Any) -> Push:
    name = _next_name()
    return Push(container_id=name, name=name, **fields)


def fresh_run(**fields: Any) -> Push:
    return running(**fields)


def unreported(**fields: Any) -> Push:
    """A run that has pushed nothing yet; its name is only the id groom would show."""
    name = _next_name()
    return Push(container_id=name, **fields)


def named(name: str, **fields: Any) -> Push:
    return Push(container_id=_next_name(), name=name, **fields)


def with_node(node: str = "plan", **fields: Any) -> Push:
    return running(current_node=node, **fields)


def on_branch(repo: str = "shop", branch: str = "main", **fields: Any) -> Push:
    return running(repo_name=repo, repo_branch=branch, **fields)


def with_gate(path: str = "gates/approve.md", question: str = "Ship it?", **fields: Any) -> Push:
    return running(file_path=path, question=question, **fields)


def with_question(question: str, **fields: Any) -> Push:
    return with_gate(question=question, **fields)


def blocked(**fields: Any) -> Push:
    return with_gate(**fields)


def finished(code: int = 0, **fields: Any) -> Push:
    return running(exit_code=code, **fields)


def stranger(**fields: Any) -> Push:
    """A run nobody pushed: an id groom never saw."""
    name = _next_name()
    return Push(container_id=name, name=name, **fields)
