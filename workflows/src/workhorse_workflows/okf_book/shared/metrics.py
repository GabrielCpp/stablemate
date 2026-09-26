"""What each turn cost, appended as it finishes, so a run's minutes, tokens and dollars are read per book afterwards."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict
from workhorse.runner.usage import TurnUsage

from workhorse_workflows.okf_book.shared.blockers import Phase

METRICS_NAME = "metrics.jsonl"


class TurnMetric(BaseModel):
    """One turn: its phase and prompt, the books it wrote, its minutes, the tokens it read and generated, and its dollars when the backend reported them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Phase
    node: str
    subjects: tuple[str, ...]
    minutes: float
    tokens_read: int = 0
    tokens_generated: int = 0
    dollars: float | None = None


def turn_metric(phase: Phase, node: str, subjects: tuple[str, ...], minutes: float, usage: TurnUsage) -> TurnMetric:
    """The turn's metric, with the tokens and dollars its backend reported."""
    read = (usage.input_tokens or 0) + (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0)
    return TurnMetric(
        phase=phase,
        node=node,
        subjects=subjects,
        minutes=minutes,
        tokens_read=read,
        tokens_generated=usage.generated_tokens or 0,
        dollars=usage.total_cost_usd,
    )


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
