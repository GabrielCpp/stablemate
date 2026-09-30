"""What a run could not finish, collected across its books and handed to the operator after the last."""
from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

BLOCKERS_DIR = "blockers"


class Phase(StrEnum):
    """The phase a blocker was found in."""

    WRITE = "write"
    EXERCISE = "exercise"


class Side(StrEnum):
    """What has to change for a blocker to clear."""

    BOOK = "book"
    OSTLER = "ostler"
    APP = "app"
    WORKFLOW = "workflow"
    ENVIRONMENT = "environment"
    UNATTRIBUTED = "unattributed"


class Blocker(BaseModel):
    """One thing the run stopped working on: a file, a page, an obligation or a scenario, the service it belongs to, and why.

    A record written before blockers named their service reads with no service.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    service: str = ""
    phase: Phase
    side: Side
    reason: str

    @property
    def key(self) -> str:
        """One key per phase and subject, so a later account of the same subject replaces the earlier one."""
        return hashlib.sha256(f"{self.phase}\0{self.subject}".encode()).hexdigest()[:16]


def record_blocker(run_dir: Path, blocker: Blocker) -> Blocker:
    folder = run_dir / BLOCKERS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    _ = (folder / f"{blocker.key}.json").write_text(blocker.model_dump_json(indent=2), encoding="utf-8")
    return blocker


def forget_blockers(run_dir: Path, phase: Phase, side: Side, service: str) -> None:
    """Drop the blockers of *phase* and *side* on *service*, so a later check that no longer finds them clears them."""
    for blocker in read_blockers(run_dir):
        if blocker.phase is phase and blocker.side is side and blocker.service == service:
            (run_dir / BLOCKERS_DIR / f"{blocker.key}.json").unlink()


def forget_every_blocker(run_dir: Path) -> None:
    """Drop every blocker, once the operator has fixed what they named."""
    for path in (run_dir / BLOCKERS_DIR).glob("*.json"):
        path.unlink()


def read_blockers(run_dir: Path) -> tuple[Blocker, ...]:
    """Every blocker recorded so far, by phase then subject."""
    folder = run_dir / BLOCKERS_DIR
    if not folder.is_dir():
        return ()
    found = (Blocker.model_validate_json(path.read_text(encoding="utf-8")) for path in folder.glob("*.json"))
    return tuple(sorted(found, key=lambda b: (list(Phase).index(b.phase), b.subject)))
