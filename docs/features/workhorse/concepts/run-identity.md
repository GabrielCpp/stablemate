---
type: concept
slug: run-identity
title: Run identity and directory resolution
---
# Run identity and directory resolution

Run identity determines which run directory a workflow starts or resumes. Explicit ids win;
parameterized runs use a stable digest, while parameterless runs use `default` at the caller.
The resolver accepts a path, a full directory name, or the id that named the directory.

- code: `workhorse/workhorse/rundir.py`

### derive_run_id
- sig: `derive_run_id(run_id: str | None, params: dict[str, Any] | None) -> str | None`
- consistency: run-id — an explicit id is returned unchanged
- does: returns `p` plus the first eight hexadecimal SHA-1 characters of canonical sorted JSON when params are non-empty and no explicit id exists
- does: returns `None` when neither an explicit id nor non-empty params exist
- returns: an id that is deterministic for equal parameter mappings
- code: `workhorse/workhorse/rundir.py::derive_run_id`
- verify: json_path(path="$.run_id", equals="psample")
- tests: `workhorse/tests/test_run_options.py::test_runs_dir_defaults_to_cwd_dot_agents_runs`

### resume_argv
- sig: `resume_argv(program: str, run_dir: Path, *, cli: str = "", profile: str = "", config_path: str = "") -> list[str]`
- does: builds `<program> run --resume-run <run_dir>` without replaying the original launch arguments
- does: appends `--cli`, `--profile`, and `--config` only when their values are non-empty
- returns: an argv suitable for resuming the existing run directory
- code: `workhorse/workhorse/rundir.py::resume_argv`

### auto_resolve
- sig: `auto_resolve(runs_dir: Path, workflow_name: str, run_id: str | None = None) -> tuple[str, Path | None]`
- does: maps a missing id to `default` and constructs `<workflow>-<id>` below `runs_dir`
- consistency: checkpoint — a missing checkpoint returns the effective id with no resume directory
- verify: absent(subject="resume directory when the checkpoint is absent")
- consistency: run-record — a terminal `run.json` record returns the effective id with no resume directory
- verify: absent(subject="resume directory when the run record is terminal")
- returns: the effective id and an existing non-terminal checkpoint directory, or `None`
- code: `workhorse/workhorse/rundir.py::auto_resolve`

### resolve_run_dir
- sig: `resolve_run_dir(spec: str, runs_dir: Path, workflow_name: str) -> Path | None`
- does: resolves an explicit path before trying the runs-dir spelling and workflow-plus-id spelling
- returns: the resolved directory when it exists, otherwise `None`
- code: `workhorse/workhorse/rundir.py::resolve_run_dir`

### find_latest_resumable
- sig: `find_latest_resumable(runs_dir: Path) -> Path | None`
- does: considers only directories with a checkpoint and a parseable non-terminal run record
- returns: the candidate with the newest checkpoint modification time, or `None`
- code: `workhorse/workhorse/rundir.py::find_latest_resumable`
- tests: `workhorse/tests/test_run_budget.py::test_budget_stop_is_resumable`

### runtime_deadline
- sig: `runtime_deadline(started_at_iso: str, budget_s: float) -> float | None`
- consistency: runtime-budget — a non-positive runtime budget returns no deadline
- verify: json_path(path="$.deadline", absent=true)
- does: anchors a positive budget to the recorded start timestamp
- returns: an absolute Unix timestamp deadline
- code: `workhorse/workhorse/rundir.py::runtime_deadline`
