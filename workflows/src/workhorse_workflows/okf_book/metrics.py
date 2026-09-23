"""What each turn cost, appended as it finishes, so a run's tokens and minutes are read per file afterwards."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.blockers import Phase

METRICS_NAME = "metrics.jsonl"


class TurnMetric(BaseModel):
    """One turn: its phase and prompt, the files or pages it worked on, the tokens packed into it, and its minutes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Phase
    node: str
    subjects: tuple[str, ...]
    tokens: int
    minutes: float


def record_turn(run_dir: Path, metric: TurnMetric) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / METRICS_NAME).open("a", encoding="utf-8") as out:
        _ = out.write(metric.model_dump_json() + "\n")


def read_metrics(run_dir: Path) -> tuple[TurnMetric, ...]:
    path = run_dir / METRICS_NAME
    if not path.is_file():
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(TurnMetric.model_validate_json(line) for line in lines if line.strip())
