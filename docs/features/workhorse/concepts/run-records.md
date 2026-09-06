---
type: concept
slug: run-records
title: Run record models
---
# Run record models

`records.py` owns the validated shapes that cross a process boundary; it performs no I/O.
`ArtifactWriter` writes these records and the driver decides whether a parsed checkpoint may be
resumed. Workflow-specific values in `params`, `inputs`, and `ctx` remain opaque.

- code: `workhorse/workhorse/records.py`
- detail: [run artifacts](../run-artifacts.md)

The public record models are `PyflowCheckpoint`, `NodeGraphCheckpoint`, `RepoObservation`,
`RunRecord`, `LaunchRecord`, and `NodeEvent`. `Checkpoint` is their checkpoint union,
`NodePhase` is the closed set `enter | done | terminal | error`, and `NodeEvent` permits
phase-specific extra keys at the top level so external scorecards can consume them without a
shape change.

### method: parse_checkpoint
- sig: `parse_checkpoint(text: str) -> Checkpoint`
- does: validates JSON against the pyflow or retired node-graph checkpoint shape
- raises: `pydantic.ValidationError` when the text is invalid or names neither checkpoint shape
- returns: the validated checkpoint model
- code: `workhorse/workhorse/records.py::parse_checkpoint`
- tests: `workhorse/tests/test_records.py::test_a_checkpoint_that_is_neither_engines_is_refused`

### method: parse_launch_record
- sig: `parse_launch_record(text: str) -> LaunchRecord`
- raises: `pydantic.ValidationError` when the text is not a launch record
- returns: the validated launch record
- code: `workhorse/workhorse/records.py::parse_launch_record`

### method: parse_run_record
- sig: `parse_run_record(text: str) -> RunRecord`
- raises: `pydantic.ValidationError` when the text is not a JSON object
- returns: the validated run record
- code: `workhorse/workhorse/records.py::parse_run_record`

### PyflowCheckpoint
- sig: `PyflowCheckpoint(engine: Literal["pyflow"], workflow: str, run_id: str, flow: str | None, state: str, params: dict[str, Any], waiting_on: str | None, inputs: dict[str, Any], ctx: Any, seq: int, updated_at: str)`
- does: identifies the pyflow state and arguments to re-enter, while carrying constructor inputs and context needed to rebuild the workflow
- code: `workhorse/workhorse/records.py::PyflowCheckpoint`

### RunRecord
- sig: `RunRecord(workflow: str, run_id: str, started_at: str, ended_at: str | None, terminal: str | None, interrupted_at: str | None, error: str | None, pid: int | None, repo_start: RepoObservation | None, repo_end: RepoObservation | None, profile: str, profile_config: dict[str, Any])`
- does: distinguishes an in-progress, interrupted, terminal, or failed run while preserving start/end repository observations and selected profile metadata
- code: `workhorse/workhorse/records.py::RunRecord`

### LaunchRecord
- sig: `LaunchRecord(argv: list[str], resume_argv: list[str], cwd: str, program: str, pid: int | None, started_at: str, resume_generation: int, container: bool)`
- does: records the process invocation and a separately safe resume invocation for an external watcher
- code: `workhorse/workhorse/records.py::LaunchRecord`

### NodeEvent
- sig: `NodeEvent(ts: str, seq: int, node: str, phase: NodePhase, **extra: Any)`
- does: validates the four event phases while retaining phase-specific extra properties at top level
- code: `workhorse/workhorse/records.py::NodeEvent`
- tests: `workhorse/tests/test_records.py::test_the_phase_set_is_closed`
