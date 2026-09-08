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
- verify: json_path(path="result.type", matches="^(PyflowCheckpoint|NodeGraphCheckpoint)$")
- raises: `pydantic.ValidationError` when the text is invalid or names neither checkpoint shape
- verify: json_path(path="exception.type", equals="ValidationError")
- returns: the validated checkpoint model
- verify: json_path(path="result.state", equals="implement")
- code: `workhorse/workhorse/records.py::parse_checkpoint`
- tests: `workhorse/tests/test_records.py::test_a_checkpoint_that_is_neither_engines_is_refused`

### method: parse_launch_record
- sig: `parse_launch_record(text: str) -> LaunchRecord`
- raises: `pydantic.ValidationError` when the text is not a launch record
- verify: json_path(path="exception.type", equals="ValidationError")
- returns: the validated launch record
- verify: json_path(path="result.type", equals="LaunchRecord")
- code: `workhorse/workhorse/records.py::parse_launch_record`

### method: parse_run_record
- sig: `parse_run_record(text: str) -> RunRecord`
- raises: `pydantic.ValidationError` when the text is not a JSON object
- verify: json_path(path="exception.type", equals="ValidationError")
- returns: the validated run record
- verify: json_path(path="result.type", equals="RunRecord")
- code: `workhorse/workhorse/records.py::parse_run_record`

### PyflowCheckpoint
- sig: `PyflowCheckpoint(engine: Literal["pyflow"], workflow: str, run_id: str, flow: str | None, state: str, params: dict[str, Any], waiting_on: str | None, inputs: dict[str, Any], ctx: Any, seq: int, updated_at: str)`
- does: identifies the pyflow state and arguments to re-enter, while carrying constructor inputs and context needed to rebuild the workflow
- code: `workhorse/workhorse/records.py::PyflowCheckpoint`

## Fields

### field: NodeGraphCheckpoint
- type: `BaseModel`
- semantics: retired YAML-engine checkpoint retained only so readers identify and refuse it instead of treating a node id as a pyflow state
- code: `workhorse/workhorse/records.py::NodeGraphCheckpoint`
- detail: [checkpoint engine selection](checkpoint-engine-selection.md)

#### field: engine
- type: `str | None`
- default: `None`
- required: false
- semantics: optional engine marker carried by a retired node-graph checkpoint
- verify: json_path(path="$.engine", equals="null")
- code: `workhorse/workhorse/records.py::NodeGraphCheckpoint`
- detail: [checkpoint engine selection](checkpoint-engine-selection.md)

#### field: workflow
- type: `str`
- default: `""`
- required: false
- semantics: workflow name retained in the retired checkpoint when present
- verify: json_path(path="$.workflow", equals="")
- code: `workhorse/workhorse/records.py::NodeGraphCheckpoint`
- detail: [checkpoint engine selection](checkpoint-engine-selection.md)

#### field: run_id
- type: `str`
- default: `""`
- required: false
- semantics: run identifier retained in the retired checkpoint when present
- verify: json_path(path="$.run_id", equals="")
- code: `workhorse/workhorse/records.py::NodeGraphCheckpoint`
- detail: [checkpoint engine selection](checkpoint-engine-selection.md)

#### field: current_id
- type: `str`
- required: true
- semantics: retired engine's current node identifier
- verify: json_path(path="$.current_id", matches="^.+$")
- semantics: presence distinguishes this shape from a pyflow checkpoint
- verify: json_path(path="$.current_id", matches="^.+$")
- code: `workhorse/workhorse/records.py::NodeGraphCheckpoint`
- detail: [checkpoint engine selection](checkpoint-engine-selection.md)
- tests: `workhorse/tests/test_records.py::test_the_engine_field_is_a_discriminator_not_a_comment`

#### field: context
- type: `dict[str, Any]`
- default: `{}`
- required: false
- semantics: opaque ambient context carried by the retired node-graph engine
- verify: json_path(path="$.context", equals="{}")
- code: `workhorse/workhorse/records.py::NodeGraphCheckpoint`
- detail: [checkpoint engine selection](checkpoint-engine-selection.md)

#### field: seq
- type: `int`
- default: `0`
- required: false
- semantics: checkpoint sequence retained by the retired engine
- verify: json_path(path="$.seq", equals=0)
- code: `workhorse/workhorse/records.py::NodeGraphCheckpoint`
- detail: [checkpoint engine selection](checkpoint-engine-selection.md)

#### field: updated_at
- type: `str`
- default: `""`
- required: false
- semantics: update timestamp retained by the retired engine when present
- verify: json_path(path="$.updated_at", equals="")
- code: `workhorse/workhorse/records.py::NodeGraphCheckpoint`
- detail: [checkpoint engine selection](checkpoint-engine-selection.md)

### field: RepoObservation
- type: `BaseModel`
- semantics: point-in-time Git observation embedded in a run record
- verify: json_path(path="$.head", matches="^[0-9a-f]{40}$")
- semantics: empty values mean the fact was not observed
- verify: json_path(path="$.head", equals="")
- code: `workhorse/workhorse/records.py::RepoObservation`
- detail: [RepoObservation fields](repo-observation-fields.md)

#### field: path
- type: `str`
- default: `""`
- required: false
- semantics: working-tree path associated with the observation
- verify: json_path(path="$.path", equals="")
- code: `workhorse/workhorse/records.py::RepoObservation`
- detail: [RepoObservation fields](repo-observation-fields.md)

#### field: root
- type: `str`
- default: `""`
- required: false
- semantics: Git worktree root observed for the path
- verify: json_path(path="$.root", equals="")
- code: `workhorse/workhorse/records.py::RepoObservation`
- detail: [RepoObservation fields](repo-observation-fields.md)

#### field: origin
- type: `str`
- default: `""`
- required: false
- semantics: origin remote URL observed for the repository
- verify: json_path(path="$.origin", equals="")
- code: `workhorse/workhorse/records.py::RepoObservation`
- detail: [RepoObservation fields](repo-observation-fields.md)

#### field: head
- type: `str`
- default: `""`
- required: false
- semantics: commit identifier at the observation moment
- verify: json_path(path="$.head", equals="")
- code: `workhorse/workhorse/records.py::RepoObservation`
- detail: [RepoObservation fields](repo-observation-fields.md)

#### field: branch
- type: `str`
- default: `""`
- required: false
- semantics: branch name at the observation moment, empty when detached or unavailable
- verify: json_path(path="$.branch", equals="")
- code: `workhorse/workhorse/records.py::RepoObservation`
- detail: [RepoObservation fields](repo-observation-fields.md)

#### field: dirty
- type: `bool | None`
- default: `None`
- required: false
- semantics: true or false when working-tree dirtiness was observed, and None when it was not observed
- verify: json_path(path="$.dirty", equals="null")
- code: `workhorse/workhorse/records.py::RepoObservation`
- detail: [RepoObservation fields](repo-observation-fields.md)
- tests: `workhorse/tests/test_gitstate.py::test_run_json_records_what_the_run_started_from_and_ended_on`, `workhorse/tests/test_gitstate.py::test_run_json_outside_a_repo_records_no_observation_at_all`

### RunRecord
- code: `workhorse/workhorse/records.py::RunRecord`
- sig: `RunRecord(workflow: str, run_id: str, started_at: str, ended_at: str | None, terminal: str | None, interrupted_at: str | None, error: str | None, pid: int | None, repo_start: RepoObservation | None, repo_end: RepoObservation | None, profile: str, profile_config: dict[str, Any])`

`RunRecord` distinguishes an in-progress, interrupted, terminal, or failed run while preserving
start/end repository observations and selected profile metadata.

### LaunchRecord
- code: `workhorse/workhorse/records.py::LaunchRecord`
- sig: `LaunchRecord(argv: list[str], resume_argv: list[str], cwd: str, program: str, pid: int | None, started_at: str, resume_generation: int, container: bool)`

`LaunchRecord` records the process invocation and a separately safe resume invocation for an external watcher.

### NodeEvent
- code: `workhorse/workhorse/records.py::NodeEvent`
- tests: `workhorse/tests/test_records.py::test_the_phase_set_is_closed`
- sig: `NodeEvent(ts: str, seq: int, node: str, phase: NodePhase, **extra: Any)`

`NodeEvent` validates the four event phases while retaining phase-specific extra properties at
the top level.
