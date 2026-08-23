"""The records a run writes to disk and reads back.

`checkpoint.json`, `run.json` and `events.jsonl` are the files that survive the process,
so they are the ones that get parsed rather than trusted. Provenance is not the axis: a
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


class RepoObservation(BaseModel):
    """What git said about a working tree at one moment — a fact, not a claim.

    Written by :mod:`workhorse.gitstate`, which observes rather than predicts: the
    engine drives arbitrary workflows over arbitrary repos, so a node, or the agent
    inside a turn, may commit, branch, rebase or check out at any point, and the cwd
    may not be a working tree at all. Two observations that differ mean something moved
    HEAD between them, which is precisely what a reader would otherwise have no way to
    discover — and nothing here asserts they should have been equal.

    Every field defaults to empty/None, and empty means *not observed*. ``dirty`` is
    tri-state for that reason: None is "did not look, or could not tell", never "clean".
    """

    path: str = ""
    head: str = ""
    branch: str = ""
    dirty: bool | None = None


class RunRecord(BaseModel):
    """`run.json` — what a run directory says about itself between processes.

    Small, and load-bearing anyway: `terminal` is what `--auto` and `--resume-latest`
    consult to tell a run that crashed from one that finished, and `started_at` is the
    anchor `WORKHORSE_MAX_RUNTIME_S` counts from, so a resumed run keeps the original
    deadline instead of restarting the clock.

    Every field carries a default because the writer is not the only thing that has
    touched this file by the time it is read: a resume meets whatever the previous
    process left, and a stopped run is one an operator is expected to inspect. A record
    with nothing in it is a legitimate parse — `started_at` empty means "no anchor
    recorded", which the reader turns into now, exactly as the `.get(...)` default it
    replaces did.
    """

    workflow: str = ""
    run_id: str = ""
    started_at: str = ""
    ended_at: str | None = None
    terminal: str | None = None
    #: Set only by an operator interrupt, and cleared by the next write. "terminal null
    #: AND interrupted_at set" reads as stopped-by-a-human, distinct from "terminal
    #: null, no stamp", which is a run still in flight (or wedged in one).
    interrupted_at: str | None = None
    error: str | None = None
    #: Advertised on telemetry too; recorded here as well so it survives with telemetry
    #: off.
    pid: int | None = None
    #: The working tree as it was when this run directory was created, carried across
    #: resumes so it keeps meaning "what the run started from" rather than "what the
    #: last process happened to see".
    repo_start: RepoObservation | None = None
    #: …and as it was when the run reached a terminal. Cleared by a resume, exactly as
    #: ``ended_at`` is: a run that picked back up has no end yet.
    repo_end: RepoObservation | None = None
    #: The config profile this run resolves its models through (`--profile`), empty for
    #: the config's top-level tables. Load-bearing, unlike the copy below: a resume with
    #: no `--profile` re-applies this one, so a run that started on a cheap model set
    #: does not silently continue on the machine's default one.
    profile: str = ""
    #: …and what that profile held when the run started, copied verbatim. Informational
    #: only — behavior comes from re-reading the file every turn, so this is never read
    #: back into the run. It is what answers "which model was at `high` in March" once
    #: the config has moved on, which the profile *name* alone cannot.
    profile_config: dict[str, Any] = Field(default_factory=dict)


class LaunchRecord(BaseModel):
    """`launch.json` — what started *this process*, for whoever outlives it.

    Separate from :class:`RunRecord` because the two answer different questions over
    different lifetimes. `run.json` is about the run and is rewritten on every profile
    record, interrupt and terminal; this is about one process, written once when it opens
    the directory and read after it is dead. A resume overwrites it rather than carrying
    it forward the way `started_at` and `repo_start` are carried, because the next
    process really was launched differently.

    It exists because a SIGKILL'd run cannot report its own death, so a supervisor has to
    notice from outside — and until now the run directory said everything about the run
    except the one thing needed to restart it.

    Every field carries a default for the same reason `RunRecord`'s do: the reader meets
    whatever the last process left, and a record with nothing in it is a legitimate parse.
    """

    #: Verbatim, as this process was actually exec'd. **Forensics — never execute it.**
    #: It may carry `--no-cache`, which deletes the run directory before starting, and
    #: `--param`/`--params-file` pointing at files that have since moved on from what the
    #: checkpoint holds. Re-running it is not a resume; it is the way to lose the run.
    argv: list[str] = Field(default_factory=list)
    #: The line that *does* resume this run, from `workhorse.rundir.resume_argv`. Run it
    #: from `cwd` below. Because `--auto` resumes a stable run dir in place, this is the
    #: whole of what a supervisor has to do.
    resume_argv: list[str] = Field(default_factory=list)
    #: The working directory the process was launched from. Both argvs mean what they say
    #: only from here — a relative `--runs-dir` or `--config` resolves against it.
    cwd: str = ""
    #: `sys.argv[0]`, called out because it is what `resume_argv[0]` is: the name that was
    #: typed, not a resolved executable. A caller that needs to `exec` it resolves it.
    program: str = ""
    #: The process that wrote this record. `run.json` also holds a pid, and after a crash
    #: the two are the same one — which is the pid a watcher probes and finds gone.
    pid: int | None = None
    #: When this process opened the directory, which is not when the run began.
    started_at: str = ""
    #: How many times this directory has been started, matching the
    #: `workhorse.resume_generation` attribute on this process's telemetry. The natural
    #: budget key for anything that resumes automatically: a run that is killed the
    #: moment it starts must not be restarted forever.
    resume_generation: int = 0
    #: True when these are container coordinates. `argv[0]`, `--config`, `--runs-dir` and
    #: `cwd` are then namespace-local paths that mean nothing on the host, so a host-side
    #: consumer must refuse this record rather than re-spawn nonsense from it.
    container: bool = False


def parse_launch_record(text: str) -> LaunchRecord:
    """Parse a `launch.json` body. Raises `ValidationError` on anything that is not one,
    matching :func:`parse_run_record` — a consumer deciding whether it can re-spawn a
    dead run is better served by a refusal than by a record of empty defaults that reads
    as a runnable command."""
    return LaunchRecord.model_validate_json(text)


def parse_run_record(text: str) -> RunRecord:
    """Parse a `run.json` body. Raises `ValidationError` on anything that is not one —
    the callers are all deciding whether a directory is resumable, and a directory
    whose `run.json` will not parse is one they skip."""
    return RunRecord.model_validate_json(text)


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
    "RunRecord",
    "parse_checkpoint",
    "parse_run_record",
]
