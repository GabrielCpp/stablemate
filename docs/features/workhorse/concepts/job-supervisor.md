---
type: concept
slug: job-supervisor
title: Detached job supervisor
---
# Detached job supervisor

The job primitive submits a command from a workflow node and lets a detached supervisor own its
execution, resource observations, output streams, wake edges, and final cost record. A command's
own result file is kept separate from the supervisor's `runner.json`, so later workflow code can
distinguish a measured failure from a missing measurement. Jobs are resumed by adoption when their
handle and fresh heartbeat still describe a live supervisor.

- code: `workhorse/workhorse/job.py`
- tests: `workhorse/tests/test_job.py`

The containment tier is `premium` when delegated Linux systemd controllers can enforce memory and
CPU, `best_effort` on other Linux hosts, and `advisory` elsewhere. Memory can terminate a job;
elapsed-time overruns only touch `wake` at doubled estimate multiples and never kill the command.

## Methods

### method: containment_tier
- sig: `containment_tier() -> str`
- does: report the strongest containment tier this machine can deliver
- returns: one of `advisory`, `best_effort`, or `premium`
- verify: json_path(path="$.tier", matches="^(advisory|best_effort|premium)$")
- code: `workhorse/workhorse/job.py::containment_tier`

### method: meets
- sig: `meets(tier: str, floor: str) -> bool`
- does: compare the delivered tier with the requested minimum
- raises: `JobError` when either tier name is unknown
- returns: `true` when the delivered tier is at least the requested floor
- verify: json_path(path="$.meets", equals=true)
- code: `workhorse/workhorse/job.py::meets`

### method: overrun_multiple
- sig: `overrun_multiple(elapsed_s: float, estimate_s: float, first: float) -> float`
- does: find the largest crossed threshold in `first`, `2*first`, `4*first`, and later powers of two
- returns: `0.0` when elapsed time, estimate, or first threshold is non-positive, or no threshold is crossed
- verify: count(subject="overrun threshold crossed at 10x estimate", equals=1)
- code: `workhorse/workhorse/job.py::overrun_multiple`

### method: submit
- sig: `submit(manifest: dict, *, job_dir: Path | str, logger: logging.Logger | None = None) -> Handle`
- does: create the job directory and persist the normalized manifest
- does: adopt the existing live job instead of launching a duplicate
- does: launch a detached supervisor after validating the command and containment floor
- raises: `JobError` when the manifest has no command or an invalid tier
- raises: `ContainmentUnavailable` when the host cannot meet `min_containment`
- returns: a `Handle` identifying the supervisor before the command starts
- verify: persists(subject="job handle before command launch")
- verify: count(subject="live supervisor processes for one repeated submission", equals=1)
- code: `workhorse/workhorse/job.py::submit`

### method: arm
- sig: `arm(job_dir: Path | str) -> Path`
- does: remove the consumed `wake` edge and create the job directory if needed
- returns: the path to the wake file
- verify: absent(subject="wake file immediately after arming")
- code: `workhorse/workhorse/job.py::arm`

### method: poll
- sig: `poll(job_dir: Path | str) -> JobStatus`
- does: classify a job from its handle, manifest, runner record, process-group liveness, heartbeat, and result file
- returns: `JobStatus` with state `missing`, `running`, `finished`, or `lost`
- verify: json_path(path="$.state", equals="finished")
- code: `workhorse/workhorse/job.py::poll`

### method: collect
- sig: `collect(job_dir: Path | str) -> RunnerResult`
- does: read the supervisor's recorded exit and resource measurements
- does: classify a supervisor with no runner record as lost
- returns: `RunnerResult` with exit code, peak RSS, wall time, kill reason, tier, and timestamps
- verify: json_path(path="$.kill_reason", equals="lost")
- code: `workhorse/workhorse/job.py::collect`

### method: kill
- sig: `kill(job_dir: Path | str, reason: str = "operator") -> RunnerResult`
- does: request a supervisor-owned kill and wait for its authoritative runner record
- does: reap the command and supervisor process groups and write a fallback result when the supervisor does not answer
- raises: `JobError` when the job has no handle
- returns: the measured or fallback `RunnerResult`
- verify: persists(subject="runner result after killing a live job")
- code: `workhorse/workhorse/job.py::kill`

### method: supervise
- sig: `supervise(job_dir: Path | str) -> int`
- does: launch the command in its own process group
- verify: created(subject="the supervised command process group")
- does: sample heartbeat while the command runs
- verify: persists(subject="job heartbeat observations")
- does: sample resident memory while the command runs
- verify: persists(subject="job resident-memory observations")
- does: process kill requests while the command runs
- verify: persists(subject="runner result after a process kill request")
- does: touch wake at each crossed overrun threshold
- verify: persists(subject="wake notification for each crossed overrun threshold")
- does: write `child.json` with the command process record
- verify: persists(subject="child.json process record")
- does: write `runner.json` with the final run record
- verify: persists(subject="runner.json final run record")
- does: write command stdout to its output file
- verify: persists(subject="command stdout file")
- does: write command stderr to its output file
- verify: persists(subject="command stderr file")
- does: leave the final wake state for waiters
- verify: persists(subject="final job wake state")
- returns: `0` after the supervisor has recorded the run
- verify: exit_status(code=0)
- code: `workhorse/workhorse/job.py::supervise`

### method: main
- sig: `main(argv: list[str] | None = None) -> int`
- does: use the supplied argument list, or the process arguments after the module name when `argv` is absent
- does: require exactly `supervise <job_dir>` as the detached supervisor invocation
- does: write the usage line to standard error when the invocation shape is invalid
- does: delegate the requested job directory to `supervise`
- returns: `2` when the invocation shape is invalid
- returns: the supervisor's integer result for a valid invocation
- verify: exit_status(code=2)
- verify: exit_status(code=0)
- code: `workhorse/workhorse/job.py::main`

## Types

### field: Handle
- type: frozen record
- semantics: identifies the supervisor and its job directory before and during execution
- verify: persists(subject="job handle identifying the supervisor and job directory")
- code: `workhorse/workhorse/job.py::Handle`
- detail: [Handle record fields](handle-record-fields.md)

#### field: job_dir
- type: `str`
- required: true
- verify: json_path(path="$.job_dir", matches="^.+$")
- semantics: filesystem directory containing the job artifacts
- verify: persists(subject="job directory containing the job artifacts")
- code: `workhorse/workhorse/job.py::Handle`
- detail: [Handle record fields](handle-record-fields.md)

#### field: pid
- type: `int`
- required: true
- verify: json_path(path="$.pid", matches="^[1-9][0-9]*$")
- semantics: supervisor process id
- verify: json_path(path="$.pid", matches="^[1-9][0-9]*$")
- code: `workhorse/workhorse/job.py::Handle`
- detail: [Handle record fields](handle-record-fields.md)

#### field: pgid
- type: `int`
- required: true
- verify: json_path(path="$.pgid", matches="^[1-9][0-9]*$")
- semantics: supervisor process-group id
- verify: json_path(path="$.pgid", matches="^[1-9][0-9]*$")
- code: `workhorse/workhorse/job.py::Handle`
- detail: [Handle record fields](handle-record-fields.md)

#### field: started_at
- type: `float`
- required: true
- verify: json_path(path="$.started_at", matches="^[1-9][0-9]*(\\.[0-9]+)?$")
- semantics: wall-clock start timestamp used for liveness and elapsed time
- verify: persists(subject="started_at timestamp in the persisted job handle")
- code: `workhorse/workhorse/job.py::Handle`
- detail: [Handle record fields](handle-record-fields.md)

#### field: tier
- type: `str`
- required: true
- verify: json_path(path="$.tier", matches="^(advisory|best_effort|premium)$")
- semantics: containment tier selected for this job
- verify: json_path(path="$.tier", equals="premium")
- code: `workhorse/workhorse/job.py::Handle`
- detail: [Handle record fields](handle-record-fields.md)

#### field: labels
- type: `dict`
- default: `{}`
- verify: count(subject="labels in a handle created without manifest labels", equals=0)
- required: false
- verify: json_path(path="$.labels.workflow", equals="nightly")
- semantics: opaque workflow labels copied into the handle
- verify: persists(subject="workflow labels copied into handle.json")
- code: `workhorse/workhorse/job.py::Handle`
- detail: [Handle record fields](handle-record-fields.md)

### field: JobStatus
- type: frozen record
- semantics: filesystem-observable running/finished/lost state and result readiness
- verify: json_path(path="$.state", equals="finished")
- code: `workhorse/workhorse/job.py::JobStatus`
- detail: [Job status field selection](job-status-field-selection.md)

#### field: state
- type: `str`
- required: true
- verify: json_path(path="$.state", matches="^(running|finished|lost|missing)$")
- semantics: `running`, `finished`, `lost`, or `missing`
- verify: json_path(path="$.state", matches="^(running|finished|lost|missing)$")
- code: `workhorse/workhorse/job.py::JobStatus`
- detail: [Job status field selection](job-status-field-selection.md)

#### field: alive
- type: `bool`
- required: true
- verify: json_path(path="$.alive", equals=true)
- semantics: process group and heartbeat both indicate a live supervisor
- verify: json_path(path="$.alive", equals=true)
- code: `workhorse/workhorse/job.py::JobStatus`
- detail: [Job status field selection](job-status-field-selection.md)

#### field: elapsed_s
- type: `float`
- required: true
- verify: json_path(path="$.elapsed_s", matches="^(0|[1-9][0-9]*)(\\.[0-9]+)?$")
- semantics: elapsed wall time observed for the job
- verify: json_path(path="$.elapsed_s", matches="^[0-9]+(\\.[0-9]+)?$")
- code: `workhorse/workhorse/job.py::JobStatus`
- detail: [Job status field selection](job-status-field-selection.md)

#### field: estimate_s
- type: `float`
- required: true
- verify: json_path(path="$.estimate_s", equals=10.0)
- semantics: submitter's predicted duration
- verify: json_path(path="$.estimate_s", equals=10.0)
- code: `workhorse/workhorse/job.py::JobStatus`
- detail: [Job status field selection](job-status-field-selection.md)

#### field: overrun_multiple
- type: `float`
- required: true
- verify: json_path(path="$.overrun_multiple", equals=20.0)
- semantics: largest doubled estimate threshold crossed while running, or `0.0`
- verify: json_path(path="$.overrun_multiple", equals=20.0)
- code: `workhorse/workhorse/job.py::JobStatus`
- detail: [Job status field selection](job-status-field-selection.md)

#### field: result_ready
- type: `bool`
- required: true
- verify: json_path(path="$.result_ready", equals=true)
- semantics: the manifest-selected result file exists
- verify: json_path(path="$.result_ready", equals=true)
- code: `workhorse/workhorse/job.py::JobStatus`
- detail: [Job status field selection](job-status-field-selection.md)

#### field: tier
- type: `str`
- required: true
- verify: json_path(path="$.tier", matches="^(advisory|best_effort|premium)$")
- semantics: containment tier recorded in the handle
- verify: json_path(path="$.tier", equals="premium")
- code: `workhorse/workhorse/job.py::JobStatus`
- detail: [Job status field selection](job-status-field-selection.md)

### field: RunnerResult
- type: frozen record
- semantics: supervisor-owned cost and termination record
- verify: persists(subject="runner.json final run record")
- code: `workhorse/workhorse/job.py::RunnerResult`
- detail: [Runner result field selection](runner-result-field-selection.md)

#### field: exit_code
- type: `int | None`
- required: true
- verify: json_path(path="$.exit_code", matches="^(None|-?[0-9]+)$")
- semantics: command exit code for a completed command
- verify: json_path(path="$.exit_code", equals=3)
- semantics: `null` when the supervisor lost the command
- verify: json_path(path="$.exit_code", matches="^null$")
- code: `workhorse/workhorse/job.py::RunnerResult`
- detail: [Runner result field selection](runner-result-field-selection.md)

#### field: peak_rss_mb
- type: `float`
- required: true
- verify: json_path(path="$.peak_rss_mb", matches="^(6[5-9]|[7-9][0-9]|[1-9][0-9]{2,})(\\.[0-9])?$")
- semantics: highest resident memory observed for the command tree
- code: `workhorse/workhorse/job.py::RunnerResult`
- detail: [Runner result field selection](runner-result-field-selection.md)

#### field: wall_s
- type: `float`
- required: true
- verify: json_path(path="$.wall_s", matches="^(0|[1-9][0-9]*)(\\.[0-9]{1,3})?$")
- semantics: total observed wall time
- verify: json_path(path="$.wall_s", matches="^[0-9]+(\\.[0-9]{1,3})?$")
- code: `workhorse/workhorse/job.py::RunnerResult`
- detail: [Runner result field selection](runner-result-field-selection.md)

#### field: kill_reason
- type: `str`
- required: true
- verify: json_path(path="$.kill_reason", equals="")
- semantics: empty for ordinary completion, otherwise `memory`, `operator`, or `lost`
- verify: json_path(path="$.kill_reason", matches="^(|memory|operator|lost)$")
- code: `workhorse/workhorse/job.py::RunnerResult`
- detail: [Runner result field selection](runner-result-field-selection.md)

#### field: tier
- type: `str`
- required: true
- verify: json_path(path="$.tier", matches="^(advisory|best_effort|premium)$")
- semantics: containment tier under which the measurement was made
- verify: json_path(path="$.tier", equals="premium")
- code: `workhorse/workhorse/job.py::RunnerResult`
- detail: [Runner result field selection](runner-result-field-selection.md)

#### field: started_at
- type: `float`
- required: true
- verify: json_path(path="$.started_at", matches="^(?!0(?:\\.0+)?$)[0-9]+(\\.[0-9]+)?$")
- semantics: start timestamp
- verify: json_path(path="$.started_at", equals=1700000000.0)
- code: `workhorse/workhorse/job.py::RunnerResult`
- detail: [Runner result field selection](runner-result-field-selection.md)

#### field: finished_at
- type: `float`
- required: true
- verify: json_path(path="$.finished_at", matches="^(?!0(?:\\.0+)?$)[0-9]+(\\.[0-9]+)?$")
- semantics: completion or loss timestamp
- verify: json_path(path="$.finished_at", matches="^[0-9]+(\\.[0-9]+)?$")
- code: `workhorse/workhorse/job.py::RunnerResult`
- detail: [Runner result field selection](runner-result-field-selection.md)

### field: JobError
- type: `RuntimeError` subclass
- semantics: submission or inspection failed and the caller must decide the workflow response
- verify: json_path(path="$.exception.type", equals="JobError")
- code: `workhorse/workhorse/job.py::JobError`

### field: ContainmentUnavailable
- type: `JobError` subclass
- semantics: the machine cannot satisfy the manifest's minimum containment floor
- verify: json_path(path="$.exception.type", equals="ContainmentUnavailable")
- code: `workhorse/workhorse/job.py::ContainmentUnavailable`
