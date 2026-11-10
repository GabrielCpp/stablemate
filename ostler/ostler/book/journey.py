"""A journey is a user's path through the service: many steps, taken from an
epic's happy path. ostler walks it on the model and on the surface at the same
time. A step is whatever the service's surface performs: an endpoint call, a
screen action, a command. Between the steps, the author states what the user
sees listed and what the surface itself shows."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Iterable

from ostler.book.outcome import Outcome
from ostler.book.status import Status


@dataclass(frozen=True)
class Given:
    """A request performed on the model and the surface before the journey, and
    the request that undoes it afterwards: a store taken down, a clock moved."""

    request: object
    undo: object | None = None

    def __str__(self) -> str:
        return f"given {self.request}"


@dataclass(frozen=True)
class Listed:
    """The author's claim about the list: these things, in this order, and
    nothing else. ostler reads each one's current row off the model and compares
    it with what the surface lists, after taking out the rows the model listed
    when the journey began."""

    of: tuple[object, ...]

    def __init__(self, *of: object):
        object.__setattr__(self, "of", of)

    def __str__(self) -> str:
        return "listed: " + (", ".join(str(f) for f in self.of) or "nothing")


@dataclass(frozen=True)
class Check:
    """A claim about the surface itself, not the list: a label, a disabled
    button, a banner. `probe(surface)` returns None when it holds, else what
    was seen instead."""

    claim: str
    probe: Callable[[Any], str | None]

    def __str__(self) -> str:
        return f"check {self.claim}"


@dataclass(frozen=True)
class Undo:
    given: Given

    def __str__(self) -> str:
        return f"no longer: {self.given}"


@dataclass(frozen=True)
class Seen:
    """What one step showed: the rows the surface listed afterwards and the
    body of the reply, when the step has one."""

    rows: tuple[object, ...] = ()
    body: Any = None


def masked(value: Any, *names: str) -> Any:
    """The value with every field called one of `names` removed, at any depth."""
    if isinstance(value, dict):
        return {k: masked(v, *names) for k, v in value.items() if k not in names}
    if isinstance(value, (list, tuple)):
        return [masked(v, *names) for v in value]
    return value


def pluck(value: Any, path: str) -> list[Any]:
    """Every value at a path such as `stages[].lines[].quantity`, flat."""
    items = [value]
    for part in path.split("."):
        many = part.endswith("[]")
        name = part[:-2] if many else part
        found: list[Any] = []
        for item in items:
            got = item[name] if name else item
            found.extend(got) if many else found.append(got)
        items = found
    return items


def difference(first: Any, second: Any, path: str = "") -> str | None:
    """Where two values first differ, by path, or None when they are equal."""
    if dataclasses.is_dataclass(first) and not isinstance(first, type):
        first = dataclasses.asdict(first)
    if dataclasses.is_dataclass(second) and not isinstance(second, type):
        second = dataclasses.asdict(second)
    if isinstance(first, dict) and isinstance(second, dict):
        for key in [*first, *(k for k in second if k not in first)]:
            if key not in second:
                return f"{path}.{key}: only the first has it ({first[key]!r})".lstrip(".")
            if key not in first:
                return f"{path}.{key}: only the second has it ({second[key]!r})".lstrip(".")
            found = difference(first[key], second[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(first, (list, tuple)) and isinstance(second, (list, tuple)):
        for n in range(max(len(first), len(second))):
            if n >= len(first):
                return f"{path}[{n}]: only the second has it ({second[n]!r})"
            if n >= len(second):
                return f"{path}[{n}]: only the first has it ({first[n]!r})"
            found = difference(first[n], second[n], f"{path}[{n}]")
            if found:
                return found
        return None
    return None if first == second else f"{path or 'value'}: {first!r} against {second!r}"


@dataclass(frozen=True)
class Same:
    """What two steps saw is equal once every field named in `but` is removed
    at any depth. It compares the reply bodies when both steps have one, else
    the rows they listed."""

    first: object
    second: object
    but: tuple[str, ...] = ()

    def __str__(self) -> str:
        return f"same: {self.first} and {self.second}" + (f" but for {', '.join(self.but)}" if self.but else "")


@dataclass(frozen=True)
class Relates:
    """A claim about what several steps saw together: `holds(*seen)` returns
    None when it holds, else what it saw."""

    claim: str
    steps: tuple[object, ...]
    holds: Callable[..., str | None]

    def __str__(self) -> str:
        return f"relates: {self.claim}"


@dataclass(frozen=True)
class Shows:
    """The author's literal rows for what one step returned: the example table
    for a value the model does not compute."""

    step: object
    rows: tuple[object, ...]

    def __init__(self, step: object, *rows: object):
        object.__setattr__(self, "step", step)
        object.__setattr__(self, "rows", rows)

    def __str__(self) -> str:
        return f"shows: {self.step}: " + (", ".join(str(r) for r in self.rows) or "nothing")


@dataclass(frozen=True)
class Refused:
    """The author's claim that the app turns this step away with `status` (and
    `message`, when given). For a read the model does not carry, where no rule
    can say so: the step is taken on the surface alone. On a step the model
    carries the claim is a rule's to make, and this is a mistake."""

    step: object
    status: Status
    message: str | None = None

    def __str__(self) -> str:
        return f"refused: {self.step} answers {self.status}" + (f" {self.message}" if self.message else "")


class Journey:
    """Subclass per journey. The docstring is the story. `steps` yields the
    surface's actions and the author's claims; `given` names the conditions in
    force for the whole walk. Journeys share one surface and one model, in
    turn. `alone = True` gives a journey a reset surface and a new model, and
    resets again after it: for a story that moves the clock, takes a
    dependency down or counts across the whole account."""

    given: tuple[Given, ...] = ()
    lang: str = "en"
    alone: bool = False

    def steps(self, today: date) -> Iterable[object]:
        raise NotImplementedError

    @classmethod
    def title(cls) -> str:
        return cls.__name__

    @classmethod
    def story(cls) -> str:
        return (cls.__doc__ or "").strip()


@dataclass
class StepResult:
    step: object
    model: Outcome | None
    app: Outcome | None
    model_rows: tuple[object, ...]
    app_rows: tuple[object, ...]
    ok: bool
    note: str = ""
    trace: str = ""
    text: str = ""
    known: Any = None
    skipped: str = ""


@dataclass
class JourneyResult:
    journey: type[Journey]
    surface: str
    steps: list[StepResult] = field(default_factory=list)
    state: str = ""

    @property
    def ok(self) -> bool:
        return all(step.ok for step in self.steps)

    @property
    def defects(self) -> list[Any]:
        """The known defects this journey met, once each."""
        return list(dict.fromkeys(step.known for step in self.steps if step.known is not None))

    @property
    def skipped(self) -> str:
        return next((step.skipped for step in self.steps if step.skipped), "")

    @property
    def verdict(self) -> str:
        if not self.ok:
            return "FAIL"
        if self.skipped:
            return "SKIP"
        return "KNOWN" if self.defects else "PASS"
