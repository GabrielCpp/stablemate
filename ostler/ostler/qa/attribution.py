"""Whose fault a failed check is, read from what its request got back, and the grouping of failures that share one cause."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

UNREACHABLE = "could not connect"
SAMPLE_CHARS = 300
CAPABILITY_FAULT = "capability"


class Cause(StrEnum):
    """The kind of defect a failed check shows, which decides who can fix it."""

    BOOK = "book"
    ARRANGEMENT = "arrangement"
    ENVIRONMENT = "environment"
    APP = "app"
    UNATTRIBUTED = "unattributed"


@dataclass(frozen=True)
class Attribution:
    """A failed check's cause, the precondition page it blames, the reply status it saw, the route shape it asked, and the capability the stack lacks when that is why it failed."""

    cause: Cause
    precondition: str = ""
    status: str = ""
    shape: str = ""
    gap: str = ""


NO_ATTRIBUTION = Attribution(Cause.UNATTRIBUTED)


def route_shape(method: str, path: str) -> str:
    """The method and first path segment of a request, so the checks one route family fails group together."""
    segment = next((part for part in path.split("/") if part), "")
    return f"{method} /{segment}/…" if segment else f"{method} /"


class ExchangeEvidence(BaseModel):
    """What a failed check's last request asked and got, and which precondition issued the credential it sent."""

    model_config = ConfigDict(frozen=True)

    method: str
    path: str
    status: int | None
    expected: tuple[int, ...] | None
    credential_sent: bool
    precondition: str


class FaultEvidence(BaseModel):
    """The book-fixture fault a failed check met: its class, the fixture and the page that declares it."""

    model_config = ConfigDict(frozen=True)

    fault_class: str
    fixture: str
    page: str


class CommandEnding(BaseModel):
    """How the command a failed check observed ended, as the harness record states it."""

    model_config = ConfigDict(frozen=True, strict=True)

    exit_code: int
    stderr: str = ""

    def text(self) -> str:
        return f"exit {self.exit_code}, stderr: {self.stderr}" if self.stderr else f"exit {self.exit_code}, stderr empty"


class CheckEvidence(BaseModel):
    """What one failed harness check recorded about why it failed, validated once as it leaves the harness."""

    model_config = ConfigDict(frozen=True)

    fault: FaultEvidence | None = None
    exchange: ExchangeEvidence | None = None
    raised: str = ""
    command_ending: CommandEnding | None = None


def attribute(evidence: CheckEvidence) -> Attribution:
    """The cause of one failed harness check, by the first rule its evidence meets; no rule met leaves it unattributed."""
    fault = evidence.fault
    if fault is not None:
        if fault.fault_class == CAPABILITY_FAULT:
            return Attribution(Cause.ENVIRONMENT, fault.page or fault.fixture, gap=fault.fixture.replace("-", " "))
        if fault.fault_class == "environment":
            return Attribution(Cause.ENVIRONMENT, fault.page or fault.fixture)
        if fault.page:
            return Attribution(Cause.ARRANGEMENT, fault.page)
    exchange = evidence.exchange
    if exchange is None:
        return Attribution(Cause.BOOK if evidence.command_ending is not None else Cause.UNATTRIBUTED)
    shape = route_shape(exchange.method, exchange.path)
    status = exchange.status
    if status is None:
        return Attribution(Cause.ENVIRONMENT, status=UNREACHABLE, shape=shape)
    seen = str(status)
    if evidence.raised:
        return Attribution(Cause.UNATTRIBUTED, status=seen, shape=shape)
    if status >= 500:
        return Attribution(Cause.APP, status=seen, shape=shape)
    if status == 404 and "{" in exchange.path:
        return Attribution(Cause.BOOK, status=seen, shape=shape)
    if status in (401, 403) and _expects_success(exchange.expected):
        if exchange.precondition:
            return Attribution(Cause.ARRANGEMENT, exchange.precondition, seen)
        if not exchange.credential_sent:
            return Attribution(Cause.BOOK, status=seen, shape=shape)
        return Attribution(Cause.UNATTRIBUTED, status=seen, shape=shape)
    return Attribution(Cause.BOOK, status=seen, shape=shape)


def _expects_success(expected: tuple[int, ...] | None) -> bool:
    return expected is None or all(code < 400 for code in expected)


@dataclass(frozen=True)
class Signature:
    """Every failed check that shares one cause, precondition, status, route shape and absent capability, with how many there are and one of them."""

    cause: Cause
    precondition: str
    status: str
    shape: str
    count: int
    sample: str
    gap: str = ""

    def text(self) -> str:
        """The signature as one line an attendant reads."""
        if self.gap:
            return f"gapped: {self.gap} absent"
        where = self.precondition or self.shape or "no request"
        status = f" answered {self.status}" if self.status else ""
        return f"{self.cause.value}: {where}{status}"


def signatures(failures: Iterable[tuple[Attribution, str]]) -> list[Signature]:
    """Group attributed failures by their key, most frequent first, keeping the first failure's text as the sample."""
    counts: dict[Attribution, int] = {}
    samples: dict[Attribution, str] = {}
    for attribution, text in failures:
        counts[attribution] = counts.get(attribution, 0) + 1
        _ = samples.setdefault(attribution, text)
    return sorted(
        (Signature(key.cause, key.precondition, key.status, key.shape, count, samples[key], key.gap) for key, count in counts.items()),
        key=lambda signature: (-signature.count, signature.cause.value, signature.precondition, signature.shape, signature.status),
    )
