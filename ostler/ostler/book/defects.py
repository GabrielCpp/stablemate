"""The defects a book declares, the ones a run met, and the report that names
them. A declaration nobody exercises is stale, and the run says so."""

from __future__ import annotations

from typing import Any, Iterable, Protocol, Sequence

from ostler.book.journey import JourneyResult
from ostler.book.model import Defect
from ostler.book.search import actions_of
from ostler.book.service import Service


def declared(service: Service[Any], module: str) -> list[tuple[type, Defect[Any, Any]]]:
    """Every defect the service's actions declare, with the action that declares it."""
    return [(action, defect) for action in actions_of(service, module) for defect in action.defects]


class Reported(Protocol):
    """What a defect report reads off a journey, the cells or the inputs."""

    @property
    def defects(self) -> list[Defect[Any, Any]]: ...

    @property
    def journey(self) -> Any: ...


def met(results: Iterable[Reported]) -> dict[Defect[Any, Any], list[str]]:
    """For each defect a run met, the journeys that met it."""
    out: dict[Defect[Any, Any], list[str]] = {}
    for result in results:
        for defect in result.defects:
            out.setdefault(defect, []).append(result.journey.title())
    return out


def never_met(found: list[tuple[type, Defect[Any, Any]]], seen: Iterable[Defect[Any, Any]]) -> list[tuple[type, Defect[Any, Any]]]:
    taken = set(seen)
    return [(action, defect) for action, defect in found if defect not in taken]


def tally(results: list[JourneyResult]) -> str:
    verdicts = [r.verdict for r in results]
    known = verdicts.count("KNOWN")
    skipped = verdicts.count("SKIP")
    return (f"{verdicts.count('PASS')} pass, {known} known defect{'s' if known != 1 else ''}, {verdicts.count('FAIL')} fail"
            + (f", {skipped} skipped" if skipped else ""))


def describe(action: type, defect: Defect[Any, Any]) -> str:
    return f"{defect.status} {defect.message} ({action.__name__})." + (f" {defect.why.rstrip('.')}." if defect.why else "")


def section(results: Sequence[Reported], found: list[tuple[type, Defect[Any, Any]]], complete: bool = True) -> list[str]:
    """The report lines: the defects met with the journeys that met them, and
    the declared ones nobody met."""
    seen = met(results)
    lines: list[str] = []
    if seen:
        lines += ["## Known defects", ""]
        for action, defect in found:
            if defect in seen:
                lines.append(f"- {describe(action, defect)} Met in: {', '.join(seen[defect])}.")
        lines.append("")
    stale = never_met(found, seen) if complete else []
    if stale:
        lines += ["## Known defects never met (fails the run)", ""]
        lines += [f"- {describe(action, defect)}" for action, defect in stale]
        lines.append("")
    return lines
