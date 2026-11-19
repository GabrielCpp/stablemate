"""The witness report: which declared answers and which declared fields the
run never saw the service produce. A field every journey saw empty proves
nothing about the shape declared for it, so a book states what it leaves
unseen and why, and the run fails on anything else."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, cast, overload

from ostler.book.arrange import Arrange
from ostler.book.domain import Action
from ostler.book.errors import BookError
from ostler.book.model import Rule
from ostler.book.screen import Interaction
from ostler.book.state import Scene
from ostler.book.status import Status
from ostler.book.http import Endpoint, Witness, declared_paths

ITEM = re.compile(r"^((\d{1,3}|[A-Z]+(_[A-Z]+)*)(: \S.*)?|inputs)$")


LISTED_PATHS = 40


class Because(Enum):

    SHARED_GATE = "the answer comes from a gate every endpoint shares, and another endpoint shows it"
    RUNTIME = "the runtime cannot yet send the request that draws it or read the answer"
    NEVER_FILLED = "the app never fills the field for any caller"
    OUTSIDE = "only a system outside the app sets it"
    NO_ACCOUNT = "no environment the book runs in provisions an account that draws it"
    TEST_HOOK = "the endpoint is a test hook only the book calls"


ENDPOINT = "endpoint"
OUTSIDE_HAPPENING = "outside happening"
ACTION = "action"
RULE = "rule"
SCENE = "scene"

ELEMENTS = {ENDPOINT: "an endpoint", OUTSIDE_HAPPENING: "an outside happening", ACTION: "an action", RULE: "a rule", SCENE: "a scene"}
ELSEWHERE = (Because.RUNTIME, Because.OUTSIDE, Because.NO_ACCOUNT)


def kind_of(of: object) -> str:
    if isinstance(of, type):
        for kind, base in ((ENDPOINT, (Endpoint, Interaction)), (OUTSIDE_HAPPENING, Arrange), (ACTION, Action)):
            if issubclass(of, base):
                return kind
    if isinstance(of, Rule):
        return RULE
    if isinstance(of, Scene):
        return SCENE
    raise BookError(f"Unseen {of!r}: name an endpoint, an outside happening, an action, a rule or a scene")


def name_of(of: Any, kind: str) -> str:
    return cast(str, of.name if kind in (RULE, SCENE) else of.__name__)


@dataclass(frozen=True, init=False)
class Unseen:
    """Something a run is allowed not to see, and why. For an endpoint `item` is an answer,
    `"401"` or `"NOT_FOUND"`, or a field of an answer, `"200: path.to.field"` or
    `"OK: path.to.field"`, and `"inputs"` is the endpoint's input classes, which no
    call the run saw succeed could carry: `Unseen(Endpoint, "401", Because.X, "why")`.
    An outside happening, an action, a rule or a scene has no answers and takes no
    item: `Unseen(Ghost, Because.X, "why")`."""

    of: Any
    item: str
    because: Because
    why: str

    @overload
    def __init__(self, of: type[Endpoint] | type[Interaction[Any]], item: str, because: Because, why: str) -> None: ...
    @overload
    def __init__(self, of: type[Arrange[Any]] | type[Action[Any, Any]] | Rule[Any, Any] | Scene, because: Because, why: str) -> None: ...

    def __init__(self, of: Any, *args: Any, **named: Any) -> None:
        names = ("item", "because", "why") if len(args) + len(named) == 3 else ("because", "why")
        if len(args) > len(names) or any(n in named for n in names[:len(args)]) or set(named) - set(names):
            raise BookError(f"Unseen {of!r}: give the element, an item for an endpoint, a Because and a why")
        given = {**dict(zip(names, args)), **named}
        kind = kind_of(of)
        label = name_of(of, kind)
        item = given.get("item", "")
        because = given.get("because")
        why = given.get("why", "")
        if kind == ENDPOINT:
            if "item" not in given:
                raise BookError(f"Unseen {label}: {ELEMENTS[kind]} needs the answer it leaves unseen: write Unseen({label}, '401', "
                                f"Because.<reason>, why) for an answer, or Unseen({label}, '200: path.to.field', Because.<reason>, why) for a field")
            if not ITEM.match(item):
                raise BookError(f"Unseen {item!r}: write an answer such as '401' or 'NOT_FOUND', or a field of one such as "
                                f"'200: path.to.field' or 'OK: path.to.field'")
        elif "item" in given:
            raise BookError(f"Unseen {label}: {ELEMENTS[kind]} takes no item: write Unseen({label}, Because.<reason>, why)")
        if not isinstance(because, Because):
            raise BookError(f"Unseen {label} {item}".rstrip() + ": give a Because; a gap the book can close by "
                            "arranging a state, a caller or an input is closed, never declared")
        if kind != ENDPOINT and because not in ELSEWHERE:
            raise BookError(f"Unseen {label}: {ELEMENTS[kind]} is declared with Because.RUNTIME, OUTSIDE or NO_ACCOUNT, not {because.name}")
        if not isinstance(why, str) or not why.strip():
            raise BookError(f"Unseen {label} {item}".rstrip() + ": say why it stays unseen")
        object.__setattr__(self, "of", of)
        object.__setattr__(self, "item", item)
        object.__setattr__(self, "because", because)
        object.__setattr__(self, "why", why)

    @property
    def kind(self) -> str:
        return kind_of(self.of)

    @property
    def name(self) -> str:
        return name_of(self.of, self.kind)

    @property
    def key(self) -> tuple[Any, str]:
        return (self.of, self.item) if self.kind == ENDPOINT else (self.kind, self.name)

    def __str__(self) -> str:
        return f"{self.name} {self.item}" if self.item else self.name


@dataclass
class Gap:
    endpoint: type[Endpoint]
    statuses: list[Status] = field(default_factory=list)
    fields: dict[Status, list[str]] = field(default_factory=dict)

    def items(self) -> list[str]:
        return [str(s) for s in self.statuses] + [f"{s}: {p}" for s, paths in self.fields.items() for p in paths]

    def without(self, declared: set[tuple[type[Endpoint], str]], keep: bool) -> Gap:
        """The part of this gap that is declared unseen (`keep`) or is not."""
        out = Gap(self.endpoint)
        out.statuses = [s for s in self.statuses if ((self.endpoint, str(s)) in declared) is keep]
        for status, paths in self.fields.items():
            wanted = [p for p in paths if ((self.endpoint, f"{status}: {p}") in declared) is keep]
            if wanted:
                out.fields[status] = wanted
        return out


@dataclass
class WitnessReport:
    gaps: list[Gap]
    answers_seen: int
    answers_total: int
    fields_seen: int
    fields_total: int
    unseen: tuple[Unseen, ...] = ()

    @property
    def declared(self) -> set[tuple[type[Endpoint], str]]:
        return {u.key for u in self.unseen}

    @property
    def missing(self) -> set[tuple[type[Endpoint], str]]:
        return {(g.endpoint, item) for g in self.gaps for item in g.items()}

    @property
    def undeclared(self) -> list[Gap]:
        gaps = (g.without(self.declared, False) for g in self.gaps)
        return [g for g in gaps if g.statuses or g.fields]

    @property
    def stale(self) -> list[Unseen]:
        """Declared unseen, yet the run saw it or the endpoint declares no such thing."""
        return [u for u in self.unseen if u.item != "inputs" and u.key not in self.missing]

    @property
    def complete(self) -> bool:
        return not self.undeclared and not self.stale

    @property
    def summary(self) -> str:
        return (f"{self.answers_seen} of {self.answers_total} answers and "
                f"{self.fields_seen} of {self.fields_total} fields witnessed")

    def text(self, name: str, fails: bool = True) -> str:
        lines = [f"# {name}: what the run witnessed", "", self.summary + ".", ""]
        if self.unseen and any(u.item == "inputs" or u.key in self.missing for u in self.unseen):
            lines += ["## Declared unseen", ""]
            lines += [f"- {u} ({u.because.name}): {u.why}" for u in self.unseen if u.item == "inputs" or u.key in self.missing]
            lines.append("")
        if self.undeclared:
            lines += ["## Unseen, undeclared" + (" (fails the run)" if fails else ""), ""]
            for gap in self.undeclared:
                lines.append(f"### {gap.endpoint.__name__} ({gap.endpoint.route()})")
                if gap.statuses:
                    lines.append("- answers never seen: " + ", ".join(str(s) for s in gap.statuses))
                for status, paths in gap.fields.items():
                    listed = ", ".join(paths[:LISTED_PATHS])
                    if len(paths) > LISTED_PATHS:
                        rest = sorted({p.split(".", 1)[0] for p in paths[LISTED_PATHS:]})
                        listed += f", and {len(paths) - LISTED_PATHS} more under: " + ", ".join(rest)
                    lines.append(f"- {status}: fields never seen with a real value: " + listed)
                lines.append("")
        if self.stale:
            lines += ["## Declared unseen but seen, or not declared by the endpoint" + (" (fails the run)" if fails else ""), ""]
            lines += [f"- {u}: {u.why}" for u in self.stale]
            lines.append("")
        if self.complete and not self.unseen:
            lines.append("Every declared answer and field was seen.")
        return "\n".join(lines)


def merged(witnesses: Iterable[Witness]) -> Witness:
    out = Witness()
    for w in witnesses:
        out.merge(w)
    return out


def report(declared: Iterable[type[Endpoint]], seen: Witness, unseen: tuple[Unseen, ...] = ()) -> WitnessReport:
    """Over the endpoints the service declares and any others the run saw on
    one of their hosts. A call to another host belongs to another service's
    book, which is where its answers are witnessed."""
    declared = list(declared)
    hosts = {endpoint.host for endpoint in declared}
    endpoints = list(dict.fromkeys([*declared, *(e for e in seen.statuses if e.host in hosts)]))
    gaps: list[Gap] = []
    answers_seen = answers_total = fields_seen = fields_total = 0
    for endpoint in endpoints:
        gap = Gap(endpoint)
        for answer in endpoint.answers:
            answers_total += 1
            paths = declared_paths(answer.body)
            fields_total += len(paths)
            if answer.status not in seen.statuses.get(endpoint, set()):
                gap.statuses.append(answer.status)
                continue
            answers_seen += 1
            real = seen.fields.get((endpoint, answer.status), set())
            fields_seen += sum(p in real for p in paths)
            missing = [p for p in paths if p not in real]
            if missing:
                gap.fields[answer.status] = missing
        if gap.statuses or gap.fields:
            gaps.append(gap)
    return WitnessReport(gaps, answers_seen, answers_total, fields_seen, fields_total, tuple(u for u in unseen if u.kind == ENDPOINT))


def witnessed(service: Any, surface: Any) -> WitnessReport:
    ask = getattr(surface, "witnesses", None)
    seen = merged(cast(Callable[[], Iterable[Witness]], ask)()) if callable(ask) else Witness()
    return report(service.endpoints, seen, service.unseen)
