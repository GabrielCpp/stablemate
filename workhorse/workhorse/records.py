"""The records a run writes to disk and reads back.

`checkpoint.json` and `events.jsonl` are the two files that survive the process, so
they are the two that get parsed rather than trusted. Provenance is not the axis: a
checkpoint written by this engine and read an hour later has, in between, been through
a version change, a partial write, and — the docstring on `write_state_checkpoint` says
so out loud — an operator editing it by hand to unstick a run. One model owns each
direction; the writer constructs it, the reader validates it.

Nothing here does I/O. `ArtifactWriter` owns the files; this module owns their shape.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

#: The closed set of event phases. Every node visit opens with `enter` and closes with
#: `done`; `terminal` ends a run (or a nested flow's scope) and `error` marks a node the
#: run was stopped inside of.
NodePhase = Literal["enter", "done", "terminal", "error"]


class PyflowCheckpoint(BaseModel):
    """The state a Python state machine resumes from.

    `engine` is the fail-closed discriminator: the two engines shared a runs directory
    and a `--resume-latest`, and neither can make sense of the other's checkpoint.

    The fields a resume actually consumes — `state`, `params`, `inputs`, `ctx`, `flow`,
    `waiting_on` — are what this type is for. The three annotations (`workflow`,
    `run_id`, `updated_at`) are provenance nothing reads back, so they carry defaults:
    an operator who trims them at hour 30 has damaged nothing the engine needs.

    `params`, `inputs` and `ctx` stay opaque on purpose. They are a *workflow's* data,
    and the engine that carries them must not learn its vocabulary.
    """

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
    """A checkpoint from the retired YAML engine: a node id plus the ambient bag.

    Nothing writes this shape any more. It stays a member of the union so the thing
    that reads it can *recognise* it and refuse it by name, which is the whole job of
    the discriminator — a `current_id` is not a state name, and matching one against
    the other by coincidence is the failure worth preventing.
    """

    engine: str | None = None
    workflow: str = ""
    run_id: str = ""
    current_id: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    seq: int = 0
    updated_at: str = ""


#: What `checkpoint.json` may hold. Unambiguous by required field: only the pyflow
#: shape has a `state`, only the node-graph one a `current_id`.
Checkpoint = PyflowCheckpoint | NodeGraphCheckpoint

_CHECKPOINT = TypeAdapter(Checkpoint)


def parse_checkpoint(text: str) -> Checkpoint:
    """Parse a `checkpoint.json` body. Raises `ValidationError` on anything that is
    neither engine's checkpoint — the caller turns that into its own failure."""
    return _CHECKPOINT.validate_json(text)


class NodeEvent(BaseModel):
    """One line of `events.jsonl`.

    The four declared fields are the contract every consumer joins on — the OTel
    exporter pairs `enter`/`done` by `(node, seq)`, and an external scorecard windows
    provider spend against `ts`. Everything else a phase wants to carry (`next`,
    `waiting_on`, `terminal`, `error`, and the per-node-kind context the engine adds:
    `blueprint`, `prompt`, `flow`, `stand_in`) rides along as extra, top-level, exactly
    as it lands on disk today. That openness is deliberate: the extras are a *node
    kind's* detail, and the record must not become the place workhorse enumerates them.
    """

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
    "parse_checkpoint",
]
