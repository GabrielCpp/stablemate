"""`turn.json`: what one agent turn was started with, enough to start it again."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from workhorse import gitstate
from workhorse.artifacts import write_unlinked
from workhorse.records import TreeStart
from workhorse.runner.backends import AgentProfile
from workhorse.runner.spec import AgentNode


class TurnRecord(BaseModel):
    """One agent turn's settings and the working trees it started from."""

    node: str = ""
    backend: str = ""
    profile: str = ""
    power: str | None = None
    model: str | None = None
    effort: str | None = None
    silence_budget_s: float | None = None
    base_timeout_s: float | None = None
    timeout_scale: float = 1.0
    cwd: str | None = None
    add_dirs: list[str] = Field(default_factory=list)
    agent: AgentProfile | None = None
    session_chain: str = ""
    resumed_session: bool = False
    start_trees: list[TreeStart] = Field(default_factory=list)


def parse_turn_record(text: str) -> TurnRecord:
    """Parse a `turn.json` body."""
    return TurnRecord.model_validate_json(text)


@dataclass(frozen=True, slots=True)
class RenderedTurn:
    """One node's turn as it will be sent: its prompt, its trees, its settings and budgets."""

    prompt: str
    cwd: str | None
    add_dirs: tuple[str, ...]
    model: str | None
    effort: str | None
    timeout_scale: float
    base_timeout_s: float
    silence_budget_s: float
    timeout_unbounded: bool


def record_turn_start(
    node: AgentNode,
    turn: RenderedTurn,
    *,
    backend: str,
    profile: str,
    run_dir: Path,
    visit_dir: Path | None,
    session_chain: str,
    resumed: bool,
) -> None:
    """Snapshot the trees this turn may touch and write what it starts from beside its prompt.

    A failure is reported and swallowed: the record serves a later replay, never this turn.
    """
    try:
        _record(node, turn, backend=backend, profile=profile, run_dir=run_dir,
                visit_dir=visit_dir, session_chain=session_chain, resumed=resumed)
    except OSError as exc:
        print(
            f"[{node.id}] WARNING: could not record this turn's start under {run_dir}: {exc}. "
            "The turn runs, but it cannot be replayed until the run dir is writable.",
            flush=True,
        )


def _record(
    node: AgentNode,
    turn: RenderedTurn,
    *,
    backend: str,
    profile: str,
    run_dir: Path,
    visit_dir: Path | None,
    session_chain: str,
    resumed: bool,
) -> None:
    record = TurnRecord(
        node=node.id,
        backend=backend,
        profile=profile,
        power=node.power,
        model=turn.model,
        effort=turn.effort,
        silence_budget_s=None if math.isinf(turn.silence_budget_s) else turn.silence_budget_s,
        base_timeout_s=None if turn.timeout_unbounded else turn.base_timeout_s,
        timeout_scale=turn.timeout_scale,
        cwd=turn.cwd,
        add_dirs=list(turn.add_dirs),
        agent=node.agent,
        session_chain=session_chain,
        resumed_session=resumed,
        start_trees=_start_trees(turn.cwd, turn.add_dirs),
    )
    write_turn_record(record, turn.prompt, run_dir, visit_dir)


def write_turn_record(record: TurnRecord, prompt: str, run_dir: Path, visit_dir: Path | None) -> None:
    """Persist what this turn starts from, so it can be started again on its own."""
    text = record.model_dump_json(indent=2)
    write_unlinked(run_dir / record.node / "turn.json", text)
    if visit_dir is None:
        return
    visit_dir.mkdir(parents=True, exist_ok=True)
    write_unlinked(visit_dir / "turn.json", text)
    write_unlinked(visit_dir / "prompt.md", prompt)


def _start_trees(cwd: str | None, add_dirs: Sequence[str]) -> list[TreeStart]:
    """The working trees this turn may touch, as it finds them."""
    return [gitstate.snapshot_tree(path) for path in (cwd or ".", *add_dirs)]
