---
type: concept
slug: pyflow-run
title: pyflow run invocation
---
# pyflow run invocation

`RunInvocation` is the immutable boundary value passed from the CLI to `run_pyflow`.
`run_pyflow` performs reference and graph preflight, resolves or creates the stable run
directory, instantiates the selected flow, builds `RunEnv`, drives it, and finalizes
telemetry and control resources on every exit path. Resume uses the checkpoint's flow,
inputs, context, state, and parameters rather than silently taking new CLI inputs.
The live run arms one control socket after telemetry starts, reports checkpoint-backed status,
and always disarms and closes it before returning. A workflow reload re-enters from the durable
checkpoint in the same process; a core reload waits until finalization and then re-executes the
resume command. Deliberate failures are terminal and receive a failure entry in the run inbox,
while budget, interrupt, and unavailable-backend stops retain a resumable checkpoint.

- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- tests: [run terminal tests](../../../../workhorse/tests/test_run_terminal.py)
- detail: [run invocation reading guide](run-invocation-reading-guide.md)
- detail: [run invocation views](run-invocation-views.md)
- detail: [run invocation documentation](run-invocation-documentation.md)

## Fields

### field: RunInvocation
- type: frozen dataclass with registry, runs_dir, flow, run_id, params, resume_run_dir, no_cache, dry_run, context_manifest, config, and telemetry
- semantics: complete run boundary selected by the command invocation
- verify: json_path(path="$.flow", equals="selected-flow")
- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- detail: [run invocation fields](run-invocation-fields.md)

### field: params
- type: `dict[str, Any]`
- default: `{}`
- verify: count(subject="workflow params", equals=0)
- required: false
- verify: json_path(path="$.params.attempt", equals=2)
- semantics: workflow inputs for a fresh run
- verify: persists(subject="fresh-run workflow inputs in the checkpoint")
- semantics: checkpoint inputs win during resume
- verify: persists(subject="checkpoint workflow inputs across resume")

### field: registry
- type: `Registry`
- required: true
- verify: json_path(path="$.registry.name", equals="demo")
- semantics: workflow registry supplying the name, entry flow, classes, nodes, and package directory
- verify: persists(subject="registry composition root used by the run")
- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- detail: [run invocation fields](run-invocation-fields.md)

### field: runs_dir
- type: `Path`
- required: true
- verify: json_path(path="$.runs_dir", matches="^/.+")
- semantics: parent directory in which the stable run directory is resolved or created
- verify: persists(subject="stable run directory under runs_dir")
- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- detail: [run invocation fields](run-invocation-fields.md)

### field: flow
- type: `str | None`
- default: `None`
- verify: json_path(path="$.flow", equals="null")
- required: false
- verify: json_path(path="$.flow", equals="null")
- semantics: explicitly requested flow for a fresh run
- verify: persists(subject="requested flow in the run checkpoint")
- semantics: a resume keeps the checkpoint's flow
- verify: persists(subject="checkpoint flow across resume")
- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- detail: [run invocation fields](run-invocation-fields.md)

### field: run_id
- type: `str | None`
- default: `None`
- verify: json_path(path="$.run_id", absent=true)
- required: false
- verify: json_path(path="$.run_id", equals="given")
- semantics: operator-selected stable run identity, otherwise derived from workflow parameters
- verify: persists(subject="resolved run identity across resume")
- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- detail: [run invocation fields](run-invocation-fields.md)

### field: resume_run_dir
- type: `Path | None`
- default: `None`
- verify: json_path(path="$.resume_run_dir", equals="null")
- required: false
- verify: json_path(path="$.resume_run_dir", equals="/runs/demo/resume")
- semantics: explicit checkpoint directory that takes precedence over automatic run resolution
- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- detail: [run invocation fields](run-invocation-fields.md)

### field: no_cache
- type: boolean
- default: `false`
- verify: json_path(path="$.no_cache", equals=false)
- required: true
- verify: json_path(path="$.no_cache", equals=false)
- semantics: discard an automatically resolved existing run before starting fresh
- verify: removed(subject="automatically resolved existing run")
- semantics: no_cache never discards an explicit resume directory
- verify: unchanged(subject="explicit resume run directory")
- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- detail: [run invocation fields](run-invocation-fields.md)

### field: dry_run
- type: boolean
- default: `false`
- verify: json_path(path="$.dry_run", equals=false)
- required: true
- verify: json_path(path="$.dry_run", equals=false)
- semantics: preflight the graph and drive substituted nodes in a dedicated cleared run directory without arming control
- verify: absent(subject="control socket after dry-run")
- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- detail: [run invocation fields](run-invocation-fields.md)

### field: context_manifest
- type: `ManifestContext`
- default: empty manifest context
- verify: json_path(path="$.context_manifest.present", equals=false)
- required: true
- verify: json_path(path="$.context_manifest.present", equals=false)
- semantics: manifest supplied to reference preflight and carried into the run environment
- verify: json_path(path="$.run_environment.manifest.present", equals=true)
- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- detail: [run invocation fields](run-invocation-fields.md)

### field: config
- type: `RunConfig`
- default: shipped run configuration
- verify: json_path(path="$.config.capture_transcripts", equals=true)
- required: true
- verify: json_path(path="$.config.capture_transcripts", equals=true)
- semantics: runtime settings used to build the environment, record profile and launch resume arguments
- verify: persists(subject="RunConfig settings in the run launch record")
- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- detail: [run invocation fields](run-invocation-fields.md)

### field: telemetry
- type: `TelemetryHost`
- default: shipped telemetry host
- verify: created(subject="default shipped telemetry host")
- required: true
- verify: json_path(path="$.telemetry.settings.endpoint", equals="http://127.0.0.1:8787")
- semantics: telemetry host installed and started for this run at the run boundary
- verify: emitted(event="run root span", count=1)
- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- detail: [run invocation fields](run-invocation-fields.md)

## Methods

### run_pyflow
- sig: `run_pyflow(invocation: RunInvocation) -> int`
- does: preflights references and graphs before dry-run execution
- does: records the selected profile and launch/resume arguments in the resolved run artifacts
- does: arms a local control channel for a live run and exposes checkpoint-backed status
- does: ends telemetry with the first terminal outcome
- verify: emitted(event="terminal", count=1)
- does: closes the control channel on every exit path
- verify: absent(subject="run control socket after exit")
- does: disarms the control channel on every exit path
- verify: absent(subject="armed control channel after exit")
- does: hands deliberate workflow failures to the run inbox before stamping the run terminal
- does: skips the failure-handoff inbox entry for `RunBudgetExceeded` and `AgentTurnFailed`, treating them as operational stops rather than verdicts
- verify: absent(subject="inbox.jsonl after a budget stop")
- does: keeps interrupt, budget, and backend stops resumable instead of stamping a terminal checkpoint
- does: executes a core reload only after telemetry is flushed and the control channel is disarmed
- does: drives the selected workflow and returns success after a terminal `Done`
- does: records interruption, budget-stop, backend-failure, and workflow-failure outcomes in run artifacts
- verify: persists(subject="run artifact outcome")
- does: leaves policy-resumable outcomes without a terminal checkpoint
- verify: json_path(path="$.terminal", absent=true)
- returns: process exit code `0` for completion, `1` for a reported failure, and `130` for keyboard interruption
- verify: exit_status(code=0)
- code: `workhorse/workhorse/pyflow/run.py::run_pyflow`
- tests: `workhorse/tests/test_run_terminal.py::test_a_successful_run_is_stamped_terminal_not_aborted`, `workhorse/tests/test_run_terminal.py::test_the_crash_backstop_still_fires_when_nothing_finalized`, `workhorse/tests/test_reload_reentry.py::test_a_run_listens_on_its_own_dir_and_stops_listening_on_the_way_out`, `workhorse/tests/test_run_budget.py::test_a_budget_stop_leaves_the_run_resumable`, `workhorse/tests/test_failure_handoff.py::test_a_run_budget_stop_writes_no_outbox_entry`

### _open_run
- sig: `_open_run(name, runs_dir, resume_run_dir, *, run_id, params, no_cache) -> tuple[ArtifactWriter, Resume | None]`
- does: prefers an explicit resume directory, otherwise resumes the stable unfinished directory or starts fresh
- returns: writer and optional parsed resume state
- verify: persists(subject="resolved run directory")
- code: `workhorse/workhorse/pyflow/run.py::_open_run`

### _instantiate
- sig: `_instantiate(workflow_cls, inputs) -> Workflow`
- does: validates checkpoint or CLI inputs against the workflow's pydantic fields
- raises: `WorkflowFailed` with validation details when construction fails
- returns: a populated workflow instance
- verify: exit_status(code=1)
- code: `workhorse/workhorse/pyflow/run.py::_instantiate`

### _drop_retired_inputs
- sig: `_drop_retired_inputs(workflow_cls, inputs) -> tuple[dict, tuple[str, ...]]`
- does: removes checkpoint keys for fields deleted from the current workflow class
- returns: filtered inputs and sorted retired field names
- verify: absent(subject="deleted workflow input in resumed instance")
- code: `workhorse/workhorse/pyflow/run.py::_drop_retired_inputs`

### _drive_reloadable
- sig: `_drive_reloadable(wf, env, resume, *, registry, writer) -> Any`
- does: drives the workflow until it completes or a reload request unwinds the active drive frames
- does: re-imports editable workflow and source-tree packages after a workflow-only reload
- does: reads the new checkpoint, rebuilds the workflow instance, and re-enters the checkpointed state
- does: converts a CLI switch or core reload into a process-edge reload request carrying CLI and live profile
- returns: the terminal value from `drive` after the final re-entry
- verify: emitted(event="reload", count=1)
- code: `workhorse/workhorse/pyflow/run.py::_drive_reloadable`
- tests: `workhorse/tests/test_reload_reentry.py::test_a_reload_re_enters_the_same_run_on_the_code_that_was_pushed`, `workhorse/tests/test_reload_reentry.py::test_a_reload_picks_up_a_fix_to_a_library_the_workflow_imports`, `workhorse/tests/test_reload_reentry.py::test_a_core_reload_replaces_the_process_only_after_the_run_is_finalized`
- emits: `reload` telemetry with checkpoint state, flow, and replaced packages

### _exec_reload
- sig: `_exec_reload(name: str, run_dir: Path, *, cli: str = "", profile: str = "") -> int`
- does: rebuilds the resume command rather than replaying the original invocation
- does: replaces the current process image with the resume command when executable resolution succeeds
- does: prints a resumable error and returns the reserved reload exit code when re-exec fails
- verify: exit_status(code=3)
- code: `workhorse/workhorse/pyflow/run.py::_exec_reload`
- tests: `workhorse/tests/test_reload_reentry.py::test_the_re_exec_argv_is_the_resume_spelling_not_the_original_one`, `workhorse/tests/test_reload_reentry.py::test_a_re_exec_carries_the_live_profile_and_the_config_file_it_is_reading`

### _reloadable_roots
- sig: `_reloadable_roots(entry_module: str) -> list[str]`
- does: includes the entry workflow package and source-tree packages that can have changed code
- does: excludes workhorse itself, live stack modules, standard-library modules, and installed site-package modules
- returns: ordered top-level module roots to purge before workflow re-import
- verify: count(subject="source packages selected for workflow reload", equals=1)
- code: `workhorse/workhorse/pyflow/run.py::_reloadable_roots`
- tests: `workhorse/tests/test_reload_reentry.py::test_the_environment_is_kept_while_the_working_tree_is_replaced`

### _reimport
- sig: `_reimport(registry: Registry) -> tuple[Registry, list[str]]`
- does: removes cached modules under the reloadable roots and invalidates import caches
- does: imports the registry composition root and returns the registry matching the running workflow
- raises: `WorkflowFailed` when the registry has no entry or the re-import exposes no matching registry
- returns: rebuilt registry and the replaced top-level roots
- verify: visible(locator="reload log", text="re-entering")
- code: `workhorse/workhorse/pyflow/run.py::_reimport`
- tests: `workhorse/tests/test_reload_reentry.py::test_a_reload_finds_the_registry_in_its_own_composition_root`

### _status_report
- sig: `_status_report(name: str, writer: ArtifactWriter) -> dict[str, object]`
- does: reports attachment, workflow, run identity, run directory, process id, and checkpoint state
- does: reports flow, checkpoint sequence, and waiting gate when a current pyflow checkpoint is readable
- does: identifies an unreadable or retired-engine checkpoint without raising
- returns: a status payload suitable for a control-channel reply
- verify: json_path(path="$.attached", equals=true)
- code: `workhorse/workhorse/pyflow/run.py::_status_report`
- tests: `workhorse/tests/test_control_command.py::test_status_is_answered_by_the_run_and_not_by_the_run_dir`, `workhorse/tests/test_control_command.py::test_a_run_that_never_answered_reports_from_disk_and_says_which_it_is`

### _record_interrupt
- sig: `_record_interrupt(writer: ArtifactWriter) -> None`
- does: records an operator interrupt against the checkpointed state without raising a secondary error
- verify: persists(subject="interrupt record in run artifacts")
- code: `workhorse/workhorse/pyflow/run.py::_record_interrupt`

### _record_failure_handoff
- sig: `_record_failure_handoff(writer: ArtifactWriter, exc: PyflowError) -> None`
- does: identifies the failure class and state from the exception and checkpoint
- does: prefers `exc.failure_class` and falls back to the exception's class name when none is attached
- does: writes the failure class, current state, error message, run directory, checkpoint path, and turn directory into one failure inbox message
- does: appends one `name: path` line per entry in `exc.artifacts`, preserving the raise site's diagnostic map
- does: preserves the original failure when the inbox write itself fails and emits a warning
- code: `workhorse/workhorse/pyflow/run.py::_record_failure_handoff`
- tests: `workhorse/tests/test_run_terminal.py::test_a_workflow_failure_still_reports_fail_first`, `workhorse/tests/test_failure_handoff.py::test_a_workflow_failure_writes_a_diagnostic_outbox_entry`, `workhorse/tests/test_failure_handoff.py::test_a_raise_sites_own_failure_class_and_artifacts_reach_the_outbox`
- emits: `failure` inbox message
- verify: persists(subject="failure handoff in run inbox")
- verify: json_path(path="$[0].kind", equals="failure")
- verify: json_path(path="$[0].body", matches=".*node: \\w+.*")
- verify: json_path(path="$[0].body", matches=".*failure_class: \\S+.*")
- verify: json_path(path="$[0].body", matches=".*run_dir: .*")
- verify: json_path(path="$[0].reply", equals="")
