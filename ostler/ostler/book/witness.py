"""The witness report: which declared answers and which declared fields the
run never saw the service produce. A field every journey saw empty proves
nothing about the shape declared for it, so a book states what it leaves
unseen and why, and the run fails on anything else."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, cast

from ostler.book.errors import BookError
from ostler.book.status import Status
from ostler.book.http import Endpoint, Witness, declared_paths

ITEM = re.compile(r"^((\d{3}|[A-Z]+(_[A-Z]+)*)(: \S.*)?|inputs)$")


class Because(Enum):

    SHARED_GATE = "the answer comes from a gate every endpoint shares, and another endpoint shows it"
    RUNTIME = "the runtime cannot yet send the request that draws it or read the answer"
    NEVER_FILLED = "the app never fills the field for any caller"
    OUTSIDE = "only a system outside the app sets it"
    NO_ACCOUNT = "no environment the book runs in provisions an account that draws it"
    TEST_HOOK = "the endpoint is a test hook only the book calls"


@dataclass(frozen=True)
class Unseen:
    """Something a run is allowed not to see, and why. `item` is an answer,
    `"401"` or `"NOT_FOUND"`, or a field of an answer, `"200: path.to.field"` or
    `"OK: path.to.field"`. `"inputs"` is the endpoint's input classes, which no
    call the run saw succeed could carry."""

    endpoint: type[Endpoint]
    item: str
    because: Because
    why: str

    def __post_init__(self) -> None:
        if not ITEM.match(self.item):
            raise BookError(f"Unseen {self.item!r}: write an answer such as '401' or 'NOT_FOUND', or a field of one such as "
                            f"'200: path.to.field' or 'OK: path.to.field'")
        if not isinstance(self.because, Because):
            raise BookError(f"Unseen {self.endpoint.__name__} {self.item}: give a Because; a gap the book can close by "
                            f"arranging a state, a caller or an input is closed, never declared")
        if not self.why.strip():
            raise BookError(f"Unseen {self.endpoint.__name__} {self.item}: say why it stays unseen")

    @property
    def key(self) -> tuple[type[Endpoint], str]:
        return self.endpoint, self.item

    def __str__(self) -> str:
        return f"{self.endpoint.__name__} {self.item}"


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
                    lines.append(f"- {status}: fields never seen with a real value: " + ", ".join(paths))
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
    return WitnessReport(gaps, answers_seen, answers_total, fields_seen, fields_total, unseen)


def witnessed(service: Any, surface: Any) -> WitnessReport:
    ask = getattr(surface, "witnesses", None)
    seen = merged(cast(Callable[[], Iterable[Witness]], ask)()) if callable(ask) else Witness()
    return report(service.endpoints, seen, service.unseen)
