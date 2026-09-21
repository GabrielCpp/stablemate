"""The records a run writes to disk and reads back."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

NodePhase = Literal["enter", "done", "terminal", "error", "rewind"]


class PyflowCheckpoint(BaseModel):
    """The state a Python state machine resumes from."""

    engine: Literal["pyflow"] = "pyflow"
    workflow: str = ""
    run_id: str = ""
    flow: str | None = None
    state: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    waiting_on: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    ctx: Any = None
    seq: int = 0
    updated_at: str = ""


class NodeGraphCheckpoint(BaseModel):
    """A checkpoint from the retired YAML engine: a node id plus the ambient bag."""

    engine: str | None = None
    workflow: str = ""
    run_id: str = ""
    current_id: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    seq: int = 0
    updated_at: str = ""


Checkpoint = PyflowCheckpoint | NodeGraphCheckpoint

_CHECKPOINT = TypeAdapter(Checkpoint)


def parse_checkpoint(text: str) -> Checkpoint:
    """Parse a `checkpoint.json` body."""
    return _CHECKPOINT.validate_json(text)


class RepoObservation(BaseModel):
    """What git said about a working tree at one moment."""

    path: str = ""
    root: str = ""
    origin: str = ""
    head: str = ""
    branch: str = ""
    dirty: bool | None = None


class RunRecord(BaseModel):
    """`run.json` — what a run directory says about itself between processes."""

    workflow: str = ""
    run_id: str = ""
    started_at: str = ""
    ended_at: str | None = None
    terminal: str | None = None
    interrupted_at: str | None = None
    error: str | None = None
    previous_process_died_at: str | None = None
    previous_process_pid: int | None = None
    pid: int | None = None
    repo_start: RepoObservation | None = None
    repo_end: RepoObservation | None = None
    profile: str = ""
    profile_config: dict[str, Any] = Field(default_factory=dict)
    worktree_path: str = ""
    worktree_branch: str = ""


class LaunchRecord(BaseModel):
    """`launch.json` — what started *this process*, for whoever outlives it."""

    argv: list[str] = Field(default_factory=list)
    resume_argv: list[str] = Field(default_factory=list)
    cwd: str = ""
    program: str = ""
    pid: int | None = None
    started_at: str = ""
    resume_generation: int = 0
    container: bool = False


def parse_launch_record(text: str) -> LaunchRecord:
    """Parse a `launch.json` body."""
    return LaunchRecord.model_validate_json(text)


def parse_run_record(text: str) -> RunRecord:
    """Parse a `run.json` body."""
    return RunRecord.model_validate_json(text)


class NodeEvent(BaseModel):
    """One line of `events.jsonl`."""

    model_config = ConfigDict(extra="allow")

    ts: str
    seq: int
    node: str
    phase: NodePhase


__all__ = [
    "Checkpoint",
    "NodeEvent",
    "NodeGraphCheckpoint",
    "NodePhase",
    "PyflowCheckpoint",
    "RunRecord",
    "parse_checkpoint",
    "parse_run_record",
]
