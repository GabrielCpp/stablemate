"""Whose fault a failed check is, read from what its request got back, and the grouping of failures that share one cause."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

UNREACHABLE = "could not connect"
SAMPLE_CHARS = 300


class Cause(StrEnum):
    """The kind of defect a failed check shows, which decides who can fix it."""

    BOOK = "book"
    ARRANGEMENT = "arrangement"
    ENVIRONMENT = "environment"
    APP = "app"
    UNATTRIBUTED = "unattributed"


@dataclass(frozen=True)
class Attribution:
    """A failed check's cause, the precondition page it blames, the reply status it saw and the route shape it asked."""

    cause: Cause
    precondition: str = ""
    status: str = ""
    shape: str = ""


NO_ATTRIBUTION = Attribution(Cause.UNATTRIBUTED)


def route_shape(method: str, path: str) -> str:
    """The method and first path segment of a request, so the checks one route family fails group together."""
    segment = next((part for part in path.split("/") if part), "")
    return f"{method} /{segment}/…" if segment else f"{method} /"


def attribute(record: Mapping[str, Any]) -> Attribution:
    """The cause of one failed harness check, by the first rule its evidence meets; no rule met leaves it unattributed."""
    fault = record.get("fault")
    if isinstance(fault, Mapping):
        blamed = str(fault.get("page") or "")
        if fault.get("class") == "environment":
            return Attribution(Cause.ENVIRONMENT, blamed or str(fault.get("fixture") or ""))
        if blamed:
            return Attribution(Cause.ARRANGEMENT, blamed)
    exchange = record.get("exchange")
    if not isinstance(exchange, Mapping):
        return Attribution(Cause.BOOK if record.get("command_ending") is not None else Cause.UNATTRIBUTED)
    status = exchange.get("status")
    path = str(exchange.get("path") or "")
    shape = route_shape(str(exchange.get("method") or ""), path)
    if not isinstance(status, int):
        return Attribution(Cause.ENVIRONMENT, status=UNREACHABLE, shape=shape)
    seen = str(status)
    if record.get("raised"):
        return Attribution(Cause.UNATTRIBUTED, status=seen, shape=shape)
    if status >= 500:
        return Attribution(Cause.APP, status=seen, shape=shape)
    if status == 404 and "{" in path:
        return Attribution(Cause.BOOK, status=seen, shape=shape)
    if status in (401, 403) and _expects_success(exchange.get("expected")):
        issuer = str(exchange.get("precondition") or "")
        if issuer:
            return Attribution(Cause.ARRANGEMENT, issuer, seen)
        if not exchange.get("credential_sent"):
            return Attribution(Cause.BOOK, status=seen, shape=shape)
        return Attribution(Cause.UNATTRIBUTED, status=seen, shape=shape)
    return Attribution(Cause.BOOK, status=seen, shape=shape)


def _expects_success(expected: object) -> bool:
    if expected is None:
        return True
    return isinstance(expected, list) and all(isinstance(code, int) and code < 400 for code in expected)


@dataclass(frozen=True)
class Signature:
    """Every failed check that shares one cause, precondition, status and route shape, with how many there are and one of them."""

    cause: Cause
    precondition: str
    status: str
    shape: str
    count: int
    sample: str

    def text(self) -> str:
        """The signature as one line an attendant reads."""
        where = self.precondition or self.shape or "no request"
        status = f" answered {self.status}" if self.status else ""
        return f"{self.cause.value}: {where}{status}"


def signatures(failures: Iterable[tuple[Attribution, str]]) -> list[Signature]:
    """Group attributed failures by their key, most frequent first, keeping the first failure's text as the sample."""
    counts: dict[tuple[Cause, str, str, str], int] = {}
    samples: dict[tuple[Cause, str, str, str], str] = {}
    for attribution, text in failures:
        key = (attribution.cause, attribution.precondition, attribution.status, attribution.shape)
        counts[key] = counts.get(key, 0) + 1
        _ = samples.setdefault(key, text)
    return sorted(
        (Signature(*key, count=count, sample=samples[key]) for key, count in counts.items()),
        key=lambda signature: (-signature.count, signature.cause.value, signature.precondition, signature.shape, signature.status),
    )
