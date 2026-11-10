"""What ostler asks of a service's model: apply a request, list what a user
sees, copy. `Rule` is one reason a request is refused, typed on what it reads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from keyword import iskeyword
from typing import Any, Callable, Generic, Hashable, TypeVar

from ostler.book.cast import Actor
from ostler.book.outcome import Done, Flawed, Outcome, Refusal
from ostler.book.status import Status

A = TypeVar("A")
S = TypeVar("S")

QUOTED = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


@dataclass(frozen=True)
class Rule(Generic[A, S]):
    """One thing the service refuses. The message is the one the service sends,
    word for word; where the service quotes what it was sent, the message names
    the request's field in braces, `user {sub} not found`. The predicate reads
    the request, the state and the caller. `why` is the reason the product
    behaves so, in the product's words."""

    message: str
    broken_when: Callable[[A, S, Actor | None], bool]
    status: Status = 400
    why: str = ""

    @property
    def name(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.message.lower()).strip("-")

    def said(self, a: object) -> str:
        """The message for one request: each `{field}` is what the request sent there."""
        def sent(named: re.Match[str]) -> str:
            if not hasattr(a, attribute(named[1])):
                return named[0]
            value = getattr(a, attribute(named[1]))
            return "" if value is None else str(value)
        return QUOTED.sub(sent, self.message)

    def check(self, a: A, s: S, by: Actor | None) -> None:
        if self.broken_when(a, s, by):
            raise Refused(self, self.said(a))


@dataclass(frozen=True)
class Defect(Generic[A, S]):
    """A call the app is known to get wrong. The model keeps the intended
    behaviour; when `shows_when` holds for a call, the app answers `status` with
    `message` instead. A status under 400 is a success the app should not give,
    and `message` is then only the defect's name. `over` is the rule whose
    refusal the app gets wrong; without it the defect shows on a call the model
    accepts. `does` is the change the app makes when the defect shows, read like
    an action's reduce; without it the app changes nothing. `why` says what is
    wrong and since when, in the product's words."""

    message: str
    shows_when: Callable[[A, S, Actor | None], bool]
    status: Status = 500
    why: str = ""
    over: Rule[A, S] | None = None
    does: Callable[[A, S, Actor | None], Any] | None = None

    @property
    def name(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.message.lower()).strip("-")

    def shows(self, a: A, s: S, by: Actor | None) -> bool:
        return self.shows_when(a, s, by)


class Flaw(Exception):
    """A defect showed for a call: `reduced` is what the reducer made of it,
    `refused` the rule that meant to refuse it, `wrong` the change the app makes."""

    def __init__(self, defect: Defect[Any, Any], reduced: object, refused: Rule[Any, Any] | None = None,
                 wrong: object = None, said: str = ""):
        super().__init__(defect.message)
        self.defect = defect
        self.reduced = reduced
        self.refused = refused
        self.wrong = wrong
        self.said = said or (refused.message if refused is not None else "")

    def __str__(self) -> str:
        return f"known defect {self.defect.status} {self.defect.message}; meant: {self.reduced if self.reduced is not None else 'nothing changes'}"


class Refused(Exception):
    def __init__(self, rule: Rule[Any, Any], said: str = ""):
        self.rule = rule
        self.said = said or rule.message
        super().__init__(self.said)

    def as_outcome(self) -> Refusal:
        return Refusal(self.said, self.rule.status)

    def __str__(self) -> str:
        return f"refused {self.rule.status} {self.said}"


class Model:
    def __init__(self, today: date):
        self.today: date = today

    def apply(self, request: object) -> tuple[object, ...] | None:
        """Change the state, or for a read return what the user is shown."""
        raise NotImplementedError

    def rows(self) -> tuple[object, ...]:
        raise NotImplementedError

    def row(self, entity: object) -> object:
        return entity

    def meant(self, flaw: Flaw) -> Done | Refusal:
        """What the call would have answered had the defect not shown."""
        raise NotImplementedError

    def adopt(self, flawed: Flawed) -> None:
        """Take the change a defect kept the app from making."""
        raise NotImplementedError

    def undergo(self, flawed: Flawed) -> None:
        """Take the change the app makes when the defect shows."""
        raise NotImplementedError

    def lookup(self, fixture: object) -> object | None:
        """The entity a fixture stands for, or None when the model keeps none."""
        return None

    def key(self) -> Hashable:
        """The state as the planner compares it."""
        return self.rows()

    def copy(self) -> Model:
        raise NotImplementedError

    def describe(self) -> str:
        return type(self).__name__

    def perform(self, request: object) -> Outcome:
        try:
            shown = self.apply(request)
        except Refused as refused:
            return refused.as_outcome()
        except Flaw as flaw:
            return Flawed(flaw.defect, self.meant(flaw), flaw.reduced, flaw.wrong)
        return Done(self.rows() if shown is None else shown, getattr(self, "view", None))

    def explain(self, request: object) -> Rule[Any, Any] | Defect[Any, Any] | None:
        """Which rule a dry run of `request` would break, or which defect it
        would meet, or None."""
        try:
            self.copy().apply(request)
        except Refused as refused:
            return refused.rule
        except Flaw as flaw:
            return flaw.defect
        return None


def attribute(name: str) -> str:
    """The attribute of a fixture that holds a field: the field's own name, with
    an underscore after it where the name is a Python keyword, `from_`."""
    return name + "_" if iskeyword(name) else name
