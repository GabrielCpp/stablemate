"""Each lap's failed checks by cause, kept across the run, and the rule that says when a lap did not help."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ostler.qa.attribution import Cause, Signature
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

PROGRESS_NAME = "progress.json"
WRITERS_CAUSES = frozenset({Cause.BOOK, Cause.ARRANGEMENT})
UNRECORDED_STOP = "an observation this lap did not record"


class LapCounts(BaseModel):
    """One lap of a service's book: its failed checks by cause, how many claims it gapped, whether it stopped at its precondition probes before the book ran, and the repeated observation that stopped it before the book's last scenario, if one did."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str
    failures: dict[Cause, int] = {}
    gapped: int = 0
    probes_only: bool = False
    stopped_on: str = Field(default="", validation_alias=AliasChoices("stopped_on", "stopped_early"))

    @field_validator("stopped_on", mode="before")
    @classmethod
    def _recorded_as_a_flag(cls, value: object) -> object:
        if isinstance(value, bool):
            return UNRECORDED_STOP if value else ""
        return value

    @property
    def stopped_early(self) -> bool:
        return bool(self.stopped_on)

    @property
    def book(self) -> int:
        """The failed checks the book's writers own: those the book or its arrangement caused."""
        return sum(count for cause, count in self.failures.items() if cause in WRITERS_CAUSES)

    def text(self) -> str:
        """The lap as one line: its count per cause, then its gapped claims."""
        counts = ", ".join(f"{cause.value} {self.failures.get(cause, 0)}" for cause in Cause)
        return f"{counts}, gapped {self.gapped}"


class _Ledger(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    laps: tuple[LapCounts, ...] = ()


def lap_counts(service: str, signatures: Iterable[Signature], gapped: int, *, probes_only: bool = False,
               stopped_on: str = "") -> LapCounts:
    """The lap whose failed checks group into *signatures*, counted by cause. A gapped check is no failure, so only *gapped* counts it."""
    failures: dict[Cause, int] = {}
    for signature in (signature for signature in signatures if not signature.gap):
        failures[signature.cause] = failures.get(signature.cause, 0) + signature.count
    return LapCounts(service=service, failures=dict(sorted(failures.items())), gapped=gapped, probes_only=probes_only,
                     stopped_on=stopped_on)


def read_laps(records_dir: Path) -> tuple[LapCounts, ...]:
    """Every lap the run recorded, in the order they ran."""
    path = records_dir / PROGRESS_NAME
    return _Ledger.model_validate_json(path.read_text(encoding="utf-8")).laps if path.is_file() else ()


def record_lap(records_dir: Path, lap: LapCounts) -> tuple[LapCounts, ...]:
    """Add *lap* to the ledger, and return the laps of its service so far."""
    laps = (*read_laps(records_dir), lap)
    _ = (records_dir / PROGRESS_NAME).write_text(_Ledger(laps=laps).model_dump_json(indent=2), encoding="utf-8")
    return service_laps(laps, lap.service)


def service_laps(laps: Iterable[LapCounts], service: str) -> tuple[LapCounts, ...]:
    return tuple(lap for lap in laps if lap.service == service)


def stalled(laps: tuple[LapCounts, ...]) -> bool:
    """Whether the last lap left the book's writers as many failed checks as the lap it is measured against, or more.

    A lap that stopped at its probes ran no book, so its count measures only the probes. It is measured
    against the lap before it when that one stopped at its probes too, and against nothing otherwise. A
    lap that ran the book is measured against the last earlier lap that ran it. A lap that stopped early
    ran part of the book, so a lap after one is measured against it only when it stopped on the same
    observation, since the repair then left the cause that stopped both. Otherwise it got further, or
    the earlier lap never recorded what stopped it, and it is measured against nothing.
    """
    if len(laps) < 2:
        return False
    last = laps[-1]
    if last.probes_only:
        return laps[-2].probes_only and last.book >= laps[-2].book
    ran = next((lap for lap in reversed(laps[:-1]) if not lap.probes_only), None)
    if ran is None or ran.stopped_on not in ("", last.stopped_on) or ran.stopped_on == UNRECORDED_STOP:
        return False
    return last.book >= ran.book


def trend(laps: Iterable[LapCounts]) -> str:
    """The book's failed checks lap after lap, as one line, a lap that stopped at its probes or early marked so."""
    return " → ".join(_lap_text(lap) for lap in laps)


def _lap_text(lap: LapCounts) -> str:
    if lap.probes_only:
        return f"{lap.book} at the probes"
    return f"{lap.book} before the run stopped early" if lap.stopped_early else str(lap.book)
