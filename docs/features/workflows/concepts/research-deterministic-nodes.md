---
type: concept
slug: research-deterministic-nodes
title: Research deterministic nodes
---
# Research deterministic nodes

The research node package contains the deterministic work around the agent-owned gate loop:
checkout selection, program and ledger loading, resource checks, detached-job lifecycle,
artifact classification, and result publication. These nodes make no model calls. Their typed
return values are the handoff to the states documented in the [research workflow composition
root](research-workflow-composition-root.md), while the returned models themselves are documented
in [research workflow schemas](research-schemas.md).

- code: `workflows/src/workhorse_workflows/research/nodes/_blueprint.py::blueprint`
- tests: `workflows/tests/research/test_measure.py::test_a_clean_exit_with_a_well_formed_result_is_ok`
- detail: [research workflow composition root](research-workflow-composition-root.md)

## Fields

### SSH_COMMAND
- type: `str`
- default: `ssh -o StrictHostKeyChecking=accept-new`
- required: true
- semantics: per-clone SSH option allowing a previously unknown host while remaining local to the clone subprocess
- verify: json_path(path="$.SSH_COMMAND", equals="ssh -o StrictHostKeyChecking=accept-new")
- code: `workflows/src/workhorse_workflows/research/nodes/setup.py::SSH_COMMAND`

### REQUIRED
- type: `list[str]`
- default: `["code_root"]`
- required: true
- semantics: flat program manifest keys required before a research program can run
- verify: json_path(path="$.REQUIRED", equals="code_root")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::REQUIRED`

### ENVELOPE_DEFAULTS
- type: `dict[str, str | int]`
- default: `min_containment=premium, envelope_ram_gb=0, envelope_cpus=0, envelope_gpu=none, envelope_disk_gb=0`
- required: true
- semantics: resource and containment defaults used when a program manifest omits an envelope key; zero numeric limits are unbounded
- verify: json_path(path="$.ENVELOPE_DEFAULTS.envelope_gpu", equals="none")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::ENVELOPE_DEFAULTS`

### LEDGER_NAME
- type: `str`
- default: `ledger.yml`
- required: true
- semantics: program-relative filename holding cumulative extension and lead-review spend
- verify: json_path(path="$.LEDGER_NAME", equals="ledger.yml")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::LEDGER_NAME`

### CONCLUDED
- type: `tuple[str, ...]`
- default: `banked, reached, impossible`
- required: true
- semantics: ledger statuses that require explicit reauthorization before another run
- verify: count(subject="concluded research ledger statuses", equals=3)
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::CONCLUDED`

### LEDGER_HEADER
- type: `str`
- default: a comment header followed by the status and two spend keys
- required: true
- semantics: explanatory prefix written before every program ledger update
- verify: json_path(path="$.LEDGER_HEADER", matches=".*research loop.*")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::LEDGER_HEADER`

### JOBS_DIR
- type: `str`
- default: `jobs`
- required: true
- semantics: program-relative directory containing detached measurement job records
- verify: json_path(path="$.JOBS_DIR", equals="jobs")
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::JOBS_DIR`

### JOBS_GITIGNORE
- type: `str`
- default: `*.log` followed by a newline
- required: true
- semantics: ignore rule written beside job directories so large job logs do not enter the result branch
- verify: omits(subject="research result branch", text="stderr.log")
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::JOBS_GITIGNORE`

### DRY_RUN_TIMEOUT_S
- type: `float`
- default: `900.0`
- required: true
- semantics: maximum seconds a rehearsal may run inside the calling state
- verify: json_path(path="$.DRY_RUN_TIMEOUT_S", equals=900.0)
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::DRY_RUN_TIMEOUT_S`

### DRY_RUN_POLL_S
- type: `float`
- default: `1.0`
- required: true
- semantics: seconds between rehearsal runner-state reads
- verify: json_path(path="$.DRY_RUN_POLL_S", equals=1.0)
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::DRY_RUN_POLL_S`

### STDERR_TAIL_CHARS
- type: `int`
- default: `4000`
- required: true
- semantics: maximum stderr suffix retained in rehearsal and collected failure data
- verify: json_path(path="$.STDERR_TAIL_CHARS", equals=4000)
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::STDERR_TAIL_CHARS`

### RESULT_CORE
- type: `tuple[str, str]`
- default: `status, metrics`
- required: true
- semantics: result-object keys required for a measurement to classify as valid
- verify: count(subject="required research result core keys", equals=2)
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::RESULT_CORE`

### TOOLING_PACKAGES
- type: `tuple[str, str]`
- default: `workhorse, ostler`
- required: true
- semantics: installed package names whose traceback frames classify a failure as tooling-owned
- verify: count(subject="research tooling traceback package names", equals=2)
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::TOOLING_PACKAGES`

## Methods

### clone_repo
- sig: `clone_repo(logger: logging.Logger, repo_dir: str = "", repo_url: str = "", repo_branch: str = "main", workspace_root: str = "/workspace") -> RepoSetup`
- does: adopts `repo_dir` without cloning when `repo_url` is empty
- verify: count(subject="in-place research checkout adoptions", equals=1)
- does: raises a workflow failure when neither an existing repository nor a clone URL is supplied
- verify: count(subject="research checkout missing-repository failures", equals=1)
- does: clones or refreshes the repository under `workspace_root` when `repo_url` is supplied
- verify: created(subject="research checkout directory")
- does: runs `uv sync --no-sources` in a cloned repository and continues when synchronization fails
- verify: count(subject="research clone dependency synchronization attempts", equals=1)
- returns: a `RepoSetup` containing the adopted or cloned repository directory
- verify: json_path(path="$.repo_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/research/nodes/setup.py::clone_repo`
- tests: `workflows/tests/research/test_workflow.py::test_a_gate_designed_built_measured_and_approved_drives_the_program_to_its_goal`

### load_program
- sig: `load_program(logger: logging.Logger, program: str, repo_dir: str, launch_dir_path: str = "", reauthorize: bool = False) -> Program`
- does: selects the explicit program, then the nearest launch-directory manifest, repository `agents.yml`, or legacy `.agents/program`, in that order
- verify: count(subject="research program selection decisions", equals=1)
- does: rejects a selected program whose `program.yml` is absent, malformed, or missing `code_root`
- verify: count(subject="research invalid program manifest failures", equals=1)
- does: rejects a selected program whose README ladder is absent
- verify: absent(subject="selected program without its README ladder")
- does: reads the program ledger and preserves its non-negative extension, lead-review, and status values
- verify: json_path(path="$.extensions_spent", equals=0)
- does: rejects a concluded program unless `reauthorize` is true
- verify: count(subject="research concluded-program authorization failures", equals=1)
- returns: a `Program` containing resolved paths, manifest settings, ledger spend, and active run status
- verify: json_path(path="$.status", equals="active")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::load_program`
- tests: `workflows/tests/research/test_workflow.py::test_a_concluded_program_needs_a_human_before_it_runs_again`

### record_spend
- sig: `record_spend(logger: logging.Logger, repo_dir: str, program_dir: str, extensions: int = 0, lead_reviews: int = 0, status: str = "active") -> Ledger`
- does: writes the program status and cumulative spend to `<program_dir>/ledger.yml`
- verify: persists(subject="research program spend ledger")
- does: returns the exact path and values written to the ledger
- verify: json_path(path="$.path", matches="ledger\\.yml$")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::record_spend`

### check_envelope
- sig: `check_envelope(logger: logging.Logger, memory_mb: int = 0, cpus: int = 0, gpu: str = "none", disk_gb: int = 0, envelope_ram_gb: int = 0, envelope_cpus: int = 0, envelope_gpu: str = "none", envelope_disk_gb: int = 0) -> EnvelopeCheck`
- does: marks a design as not fitting when bounded RAM, CPU, or disk demand exceeds the corresponding declared program envelope
- verify: json_path(path="$.fits", equals=false)
- does: marks a design as not fitting when it requests a GPU and the program declares no GPU
- verify: json_path(path="$.reason", matches="gpu")
- does: treats zero envelope bounds as unbounded and a `none` GPU as absent
- verify: json_path(path="$.fits", equals=true)
- returns: an `EnvelopeCheck` with all detected resource mismatches joined into one reason
- verify: json_path(path="$.reason", matches=".+")
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::check_envelope`
- tests: `workflows/tests/research/test_measure.py::test_a_protocol_over_the_declared_machine_does_not_fit`

### classify_fault
- sig: `classify_fault(stderr_text: str, repo_dir: str) -> str`
- does: classifies the deepest traceback frame under the repository as `repo`
- verify: json_path(path="$.fault_locus", equals="repo")
- does: classifies a deepest installed `workhorse` or `ostler` frame as `tooling`
- verify: json_path(path="$.fault_locus", equals="tooling")
- does: returns `unknown` when no traceback frame establishes either locus
- verify: json_path(path="$.fault_locus", equals="unknown")
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::classify_fault`
- tests: `workflows/tests/research/test_measure.py::test_the_deepest_frame_decides_the_locus`

### job_dir_for
- sig: `job_dir_for(repo_dir: str, program_dir: str, gate_id: str, suffix: str = "") -> str`
- does: places each gate job under `<repo>/<program>/jobs/<gate-id>` and appends an optional suffix
- verify: json_path(path="$.job_dir", matches="/jobs/gate")
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::job_dir_for`
- tests: `workflows/tests/research/test_measure.py::test_the_job_dir_is_one_directory_per_gate_inside_the_program`

### submit_job
- sig: `submit_job(logger: logging.Logger, job_dir: str, command: list[str], cwd: str, memory_mb: int = 0, cpus: int = 0, estimate_s: float = 0.0, result_file: str = "result.json", min_containment: str = "premium", labels: dict[str, str] | None = None, probe_units_timed: int = 0) -> Job`
- does: refuses an empty command as a repository fault without submitting a job
- verify: json_path(path="$.submitted", equals=false)
- does: refuses a positive estimate with no timed calibration units as a design fault
- verify: json_path(path="$.fault_locus", equals="design")
- does: removes stale result and runner artifacts only when no job is currently running
- verify: absent(subject="stale measurement artifacts before a new submission")
- does: creates the job directory and writes a sibling `.gitignore` that excludes job logs
- verify: created(subject="measurement job directory and log ignore rule")
- does: adopts a live job in the requested directory instead of launching a duplicate
- verify: count(subject="research live-job adoptions", equals=1)
- does: removes a stale result from the experiment working directory before a new attempt
- verify: absent(subject="previous attempt result in experiment working directory")
- does: returns tooling and repository launch failures with their fault locus instead of raising them
- verify: json_path(path="$.fault_locus", matches="repo|tooling")
- returns: a `Job` carrying submission, process, wake-file, containment-tier, and estimate metadata
- verify: json_path(path="$.job_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::submit_job`
- tests: `workflows/tests/research/test_measure.py::test_an_estimate_with_no_probe_behind_it_is_refused_before_the_cpu_is_spent`

### dry_run
- sig: `dry_run(logger: logging.Logger, job_dir: str, command: list[str], cwd: str, repo_dir: str = "", result_file: str = "result.json", min_containment: str = "advisory", memory_mb: int = 0, cpus: int = 0) -> DryRun`
- does: runs the rehearsal command through the detached runner with a 900-second bound
- verify: count(subject="research detached n=1 rehearsals", equals=1)
- does: refuses an empty rehearsal command as a repository fault before creating a runner manifest
- verify: json_path(path="$.fault_locus", equals="repo")
- does: succeeds only when the runner exits zero and the declared result file exists in the job directory or experiment working directory
- verify: json_path(path="$.ok", equals=true)
- does: kills an unfinished rehearsal at the bound and preserves its stderr tail and repository fault locus
- verify: json_path(path="$.ok", equals=false)
- does: reports containment and runner submission failures as a failed rehearsal with their owning locus
- verify: json_path(path="$.reason", matches=".+")
- returns: a `DryRun` reporting success, exit code, fault locus, stderr tail, and failure reason
- verify: json_path(path="$.reason", matches=".+")
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::dry_run`
- tests: `workflows/tests/research/test_workflow.py::test_a_rehearsal_that_dies_under_the_runner_never_reaches_submission`

### watch_job
- sig: `watch_job(logger: logging.Logger, job_dir: str, seen_multiple: float = 0.0) -> JobWatch`
- does: arms the supervisor wake file before polling authoritative job state
- verify: count(subject="research wake-file arm-before-poll observations", equals=1)
- does: returns `collect` for finished, lost, or missing jobs
- verify: json_path(path="$.action", equals="collect")
- does: returns `triage` once for each newly crossed overrun multiple
- verify: json_path(path="$.action", equals="triage")
- does: returns `wait` with the wake path while the job remains below a new overrun threshold
- verify: json_path(path="$.action", equals="wait")
- does: carries the highest previously reported overrun multiple into a wait result
- verify: json_path(path="$.overrun_multiple", equals=10.0)
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::watch_job`
- tests: `workflows/tests/research/test_measure.py::test_watching_arms_the_wake_file_before_it_reads_the_state`

### result_path
- sig: `result_path(job_dir: str | Path, cwd: str, result_file: str = "") -> Path`
- does: chooses the job-directory result when present
- verify: json_path(path="$.result_path", matches="/jobs/.+/result\\.json$")
- does: otherwise chooses an existing result with the requested name in the experiment working directory
- verify: count(subject="research working-directory result fallbacks", equals=1)
- does: falls back to the job-directory path when neither location currently contains the result
- verify: json_path(path="$.result_path", matches="/jobs/.+/result\\.json$")
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::result_path`
- tests: `workflows/tests/research/test_measure.py::test_a_result_written_in_the_experiment_s_cwd_is_still_the_measurement`

### collect_job
- sig: `collect_job(logger: logging.Logger, job_dir: str, repo_dir: str = "", cwd: str = "", result_file: str = "result.json", memory_mb: int = 0) -> Collected`
- does: collects supervisor cost data and reads the experiment result without a model call
- verify: count(subject="research deterministic job collections", equals=1)
- does: archives a valid result from the experiment working directory beside the supervisor record
- verify: persists(subject="research collected result artifact")
- does: prefers the job-directory result over a same-named result left in the experiment working directory
- verify: json_path(path="$.metrics.accuracy", equals=0.9)
- does: classifies memory kills or exits at the declared ceiling as `over_resource`
- verify: json_path(path="$.outcome", equals="over_resource")
- does: classifies a lost supervisor or non-zero experiment exit as `crash`
- verify: json_path(path="$.outcome", equals="crash")
- does: classifies a missing, invalid, or incomplete result as `invalid`
- verify: json_path(path="$.outcome", equals="invalid")
- does: classifies a non-object JSON result or a result missing `status` or `metrics` as `invalid`
- verify: json_path(path="$.reason", matches="result file")
- does: classifies a clean exit with `status` and `metrics` in a JSON object as `ok` and copies its seed, control, and completion values
- verify: json_path(path="$.outcome", equals="ok")
- returns: a `Collected` carrying outcome, fault locus, runner cost, result path and parsed measurement data
- verify: json_path(path="$.result_path", matches=".+")
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::collect_job`
- tests: `workflows/tests/research/test_measure.py::test_a_clean_exit_with_a_well_formed_result_is_ok`

### kill_job
- sig: `kill_job(logger: logging.Logger, job_dir: str, reason: str = "operator") -> Collected`
- does: kills the detached job with the supplied reason and retains the supervisor's cost data
- verify: persists(subject="research killed-job cost record")
- does: reads the retained stderr suffix from the job directory into the killed result
- verify: json_path(path="$.stderr_tail", matches=".+")
- returns: a `Collected` with outcome `killed`, kill reason, exit code, resource use, elapsed time, tier, and stderr tail
- verify: json_path(path="$.outcome", equals="killed")
- code: `workflows/src/workhorse_workflows/research/nodes/measure.py::kill_job`

### publish_results
- sig: `publish_results(logger: logging.Logger, repo_dir: str, result_branch: str = "research/auto", program_dir: str = "") -> PublishResult`
- does: rejects publication when `repo_dir` is empty
- verify: count(subject="research publication missing-repository failures", equals=1)
- does: sets the research commit identity, checks out the result branch with reset, and commits all gate changes
- verify: persists(subject="research result branch commit")
- does: returns unpublished with the result branch when there are no changes to commit
- verify: json_path(path="$.published", equals=false)
- does: returns published only when pushing the result branch succeeds, otherwise leaves the local branch and reports `push_failed`
- verify: json_path(path="$.status", equals="push_failed")
- returns: a `PublishResult` containing publication status, branch, and optional push-failure status
- verify: json_path(path="$.result_branch", matches=".+")
- code: `workflows/src/workhorse_workflows/research/nodes/publish.py::publish_results`
- tests: `workflows/tests/research/test_workflow.py::test_publishing_commits_the_gate_onto_the_result_branch`
