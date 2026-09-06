---
type: concept
slug: research-schemas
title: Research workflow schemas
---
# Research workflow schemas

The research workflow uses these models at its two external-Python seams: agent replies are
validated against a declared model, and selected node results are typed values passed to later
states. State transitions otherwise bind keyword arguments directly to the receiving signature.
Every `ResearchResult` descendant ignores unknown keys and removes `None` values before validation,
so omitted agent output leaves the declared default in place. `Budget` is the separate immutable
checkpoint value carrying all five research counters and two operator grants.

- code: `workflows/src/workhorse_workflows/research/schemas.py`
- detail: [research workflow composition root](research-workflow-composition-root.md)

## Models

### method: ResearchResult
- sig: `ResearchResult(data: Any) -> ResearchResult`
- does: removes entries whose value is `None` from dictionary input before descendant validation
- verify: count(subject="research null-input normalization operations", equals=1)
- does: ignores keys not declared by the concrete research model
- verify: count(subject="research unknown-key inputs accepted", equals=1)
- code: `workflows/src/workhorse_workflows/research/schemas.py::ResearchResult`

### method: RepoSetup
- sig: `RepoSetup(repo_dir: str = "") -> RepoSetup`
- does: carries the resolved research checkout directory
- verify: json_path(path="$.repo_dir", equals="")
- code: `workflows/src/workhorse_workflows/research/schemas.py::RepoSetup`

### method: Program
- sig: `Program(repo_dir: str = "", program: str = "", program_dir: str = "", progress_path: str = "", code_root: str = "", result_branch: str = "", goal: str = "", extensions_spent: int = 0, lead_reviews_spent: int = 0, status: str = "active", min_containment: str = "premium", envelope_ram_gb: int = 0, envelope_cpus: int = 0, envelope_gpu: str = "none", envelope_disk_gb: int = 0) -> Program`
- does: carries program paths, identity, ledger counters, status, and declared machine envelope
- verify: json_path(path="$.status", equals="active")
- code: `workflows/src/workhorse_workflows/research/schemas.py::Program`

### method: Ledger
- sig: `Ledger(path: str = "", extensions: int = 0, lead_reviews: int = 0, status: str = "active") -> Ledger`
- does: carries the program-scoped counters and status written by spend recording
- verify: json_path(path="$.status", equals="active")
- code: `workflows/src/workhorse_workflows/research/schemas.py::Ledger`

### method: PublishResult
- sig: `PublishResult(published: bool = false, result_branch: str = "", status: str = "") -> PublishResult`
- does: reports whether a research result was published, its branch, and its status
- verify: json_path(path="$.published", equals=false)
- code: `workflows/src/workhorse_workflows/research/schemas.py::PublishResult`

### method: GateSelection
- sig: `GateSelection(gate_id: str = "", gate_doc_path: str = "", depends_on_satisfied: bool = false, program_killed: bool = false, rationale: str = "") -> GateSelection`
- does: carries the selected gate, document, dependency readiness, kill flag, and rationale
- verify: json_path(path="$.program_killed", equals=false)
- code: `workflows/src/workhorse_workflows/research/schemas.py::GateSelection`

### method: FailedCriterion
- sig: `FailedCriterion(criterion: str = "", expected: str = "", observed: str = "", severity: str = "") -> FailedCriterion`
- does: identifies one failed gate criterion with expected, observed, and severity values
- verify: json_path(path="$.criterion", equals="")
- code: `workflows/src/workhorse_workflows/research/schemas.py::FailedCriterion`

### method: AntiShortcutFlags
- sig: `AntiShortcutFlags(lookup_flag: bool = false, oracle_route_flag: bool = false, repair_flag: bool = false, leak_flag: bool = false) -> AntiShortcutFlags`
- does: carries the four anti-shortcut findings reported by a gate check
- verify: json_path(path="$.lookup_flag", equals=false)
- code: `workflows/src/workhorse_workflows/research/schemas.py::AntiShortcutFlags`

### method: GateCheck
- sig: `GateCheck(status: str = "", verdict: str = "", failed_criteria: list[FailedCriterion] = [], anti_shortcut_flags: AntiShortcutFlags = AntiShortcutFlags(), zero_weights_changes_output: bool = false, notes: str = "") -> GateCheck`
- does: carries the gate verdict, failed criteria, anti-shortcut findings, zero-weight result, and notes
- verify: json_path(path="$.status", equals="")
- code: `workflows/src/workhorse_workflows/research/schemas.py::GateCheck`

### method: RecordResult
- sig: `RecordResult(status: str = "", outcome: str = "", progress_updated: bool = false, result_slot_updated: bool = false, finding_path: str = "") -> RecordResult`
- does: reports result status, outcome, progress update, result-slot update, and finding path
- verify: json_path(path="$.progress_updated", equals=false)
- code: `workflows/src/workhorse_workflows/research/schemas.py::RecordResult`

### method: LeadReview
- sig: `LeadReview(verdict: str = "", kill_was_correct: bool = false, reason_class: str = "", evidence: str = "", apparatus_fix: str = "", next_direction_hint: str = "", confidence: str = "") -> LeadReview`
- does: carries the lead verdict, kill assessment, reason, evidence, apparatus fix, next-direction hint, and confidence
- verify: json_path(path="$.kill_was_correct", equals=false)
- code: `workflows/src/workhorse_workflows/research/schemas.py::LeadReview`

### method: ReviveResult
- sig: `ReviveResult(status: str = "", gate_id: str = "", finding_path: str = "", progress_updated: bool = false, gate_doc_rescoped: bool = false) -> ReviveResult`
- does: reports revival status, gate identity, finding path, progress update, and gate rescope
- verify: json_path(path="$.progress_updated", equals=false)
- code: `workflows/src/workhorse_workflows/research/schemas.py::ReviveResult`

### method: NewDirectionResult
- sig: `NewDirectionResult(status: str = "", supersedes_gate: str = "", direction_name: str = "", core_question: str = "", ruled_out: list[str] = [], new_gates: list[str] = [], readme_path: str = "", progress_reset: bool = false) -> NewDirectionResult`
- does: carries a replacement direction, superseded gate, question, ruled-out paths, new gates, README path, and reset flag
- verify: json_path(path="$.progress_reset", equals=false)
- code: `workflows/src/workhorse_workflows/research/schemas.py::NewDirectionResult`

### method: GoalReview
- sig: `GoalReview(verdict: str = "", north_star_gap: str = "", evidence_or_deadends: str = "", banked_result: str = "", new_evidence_class: str = "", next_gate_title: str = "", next_gate_question: str = "", next_gate_cheapest_kill: str = "", next_gate_controls: list[str] = [], why_closer: str = "", confidence: str = "") -> GoalReview`
- does: carries the exhausted-ladder verdict, evidence or gap, optional banked result, and extension gate proposal
- verify: json_path(path="$.verdict", equals="")
- code: `workflows/src/workhorse_workflows/research/schemas.py::GoalReview`

### method: ExtendResult
- sig: `ExtendResult(status: str = "", new_gate_id: str = "", new_gate_title: str = "", depends_on: str = "", gate_doc_path: str = "", readme_updated: bool = false, progress_updated: bool = false, moves_closer: str = "") -> ExtendResult`
- does: reports the appended gate and whether README and progress artifacts were updated
- verify: json_path(path="$.readme_updated", equals=false)
- code: `workflows/src/workhorse_workflows/research/schemas.py::ExtendResult`

### method: Probe
- sig: `Probe(units_total: int = 0, units_timed: int = 0, seconds: float = 0.0, peak_rss_mb: float = 0.0) -> Probe`
- does: carries calibration workload, timed units, elapsed seconds, and peak resident memory
- verify: json_path(path="$.units_timed", equals=0)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Probe`

### method: Design
- sig: `Design(status: str = "", hypothesis: str = "", protocol: str = "", spec_files: list[str] = [], memory_mb: int = 0, cpus: int = 0, gpu: str = "none", disk_gb: int = 0, estimate_s: float = 0.0, probe: Probe = Probe(), protocol_change: str = "", notes: str = "") -> Design`
- does: carries the proposed experiment, resource declaration, estimate, calibration probe, and scientific rework explanation
- verify: json_path(path="$.gpu", equals="none")
- code: `workflows/src/workhorse_workflows/research/schemas.py::Design`

### method: Build
- sig: `Build(status: str = "", command: list[str] = [], dry_run_command: list[str] = [], cwd: str = "", result_file: str = "result.json", code_files: list[str] = [], fault_locus: str = "", component: str = "", notes: str = "") -> Build`
- does: carries measurement and rehearsal argv, working directory, result filename, code files, and fault classification
- verify: json_path(path="$.result_file", equals="result.json")
- code: `workflows/src/workhorse_workflows/research/schemas.py::Build`

### method: DryRun
- sig: `DryRun(ok: bool = false, exit_code: int | None = None, fault_locus: str = "", stderr_tail: str = "", reason: str = "") -> DryRun`
- does: reports rehearsal success and preserves exit, fault, stderr, and reason
- verify: json_path(path="$.ok", equals=false)
- code: `workflows/src/workhorse_workflows/research/schemas.py::DryRun`
- tests: `workflows/tests/research/test_workflow.py::test_a_rehearsal_that_dies_under_the_runner_never_reaches_submission`

### method: EnvelopeCheck
- sig: `EnvelopeCheck(fits: bool = false, reason: str = "") -> EnvelopeCheck`
- does: reports whether declared resources fit the program envelope and why
- verify: json_path(path="$.fits", equals=false)
- code: `workflows/src/workhorse_workflows/research/schemas.py::EnvelopeCheck`

### method: Job
- sig: `Job(submitted: bool = false, error: str = "", fault_locus: str = "", job_dir: str = "", wake_path: str = "", pid: int = 0, pgid: int = 0, tier: str = "", started_at: float = 0.0, estimate_s: float = 0.0) -> Job`
- does: carries detached-job submission state, process identity, wake path, tier, start time, and estimate
- verify: json_path(path="$.submitted", equals=false)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Job`
- tests: `workflows/tests/research/test_workflow.py::test_an_estimate_with_no_probe_behind_it_goes_back_to_the_scientist`

### method: JobWatch
- sig: `JobWatch(action: str = "", wake_path: str = "", state: str = "", overrun_multiple: float = 0.0, elapsed_s: float = 0.0, estimate_s: float = 0.0) -> JobWatch`
- does: carries watcher action, job state, wake path, elapsed time, estimate, and crossed overrun multiple
- verify: json_path(path="$.action", equals="")
- code: `workflows/src/workhorse_workflows/research/schemas.py::JobWatch`

### method: Collected
- sig: `Collected(outcome: str = "", fault_locus: str = "", exit_code: int | None = None, peak_rss_mb: float = 0.0, wall_s: float = 0.0, kill_reason: str = "", tier: str = "", result_path: str = "", result_status: str = "", metrics: dict[str, Any] = {}, seeds: list[Any] = [], controls: list[Any] = [], n_completed: int = 0, n_planned: int = 0, stderr_tail: str = "", reason: str = "") -> Collected`
- does: carries deterministic classification, supervisor measurements, parsed result core, and completion counts
- verify: json_path(path="$.outcome", equals="")
- code: `workflows/src/workhorse_workflows/research/schemas.py::Collected`
- tests: `workflows/tests/research/test_workflow.py::test_a_crash_in_repo_code_goes_to_the_engineer_with_nobody_in_the_loop`

### method: TriageResult
- sig: `TriageResult(decision: str = "", diagnosis: str = "", fault_locus: str = "", component: str = "", fix_hint: str = "") -> TriageResult`
- does: carries the overrun decision, diagnosis, fault locus, component, and repair hint
- verify: json_path(path="$.decision", equals="")
- code: `workflows/src/workhorse_workflows/research/schemas.py::TriageResult`

## Budget

### method: Budget
- sig: `Budget(reworks: int = 0, build_fixes: int = 0, rescopes: int = 0, lead_reviews: int = 0, extensions: int = 0, lead_review_grants: int = 0, extension_grants: int = 0) -> Budget`
- does: carries per-gate rework, build-fix, and rescope counters plus run-wide review and extension counters and operator grants
- verify: json_path(path="$.reworks", equals=0)
- does: rejects in-place mutation by remaining frozen after construction
- verify: unchanged(subject="budget", except_fields=[])
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget`

### method: fresh_gate
- sig: `fresh_gate() -> Budget`
- does: returns a copy with per-gate counters reset while preserving run-wide counters and grants
- verify: json_path(path="$.reworks", equals=0)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget.fresh_gate`

### method: reworked
- sig: `reworked() -> Budget`
- does: returns a copy with reworks increased by one
- verify: count(subject="research rework counter increments", equals=1)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget.reworked`

### method: built
- sig: `built() -> Budget`
- does: returns a copy with build_fixes increased by one
- verify: count(subject="research build-fix counter increments", equals=1)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget.built`

### method: rescoped
- sig: `rescoped() -> Budget`
- does: returns a copy with rescopes increased by one
- verify: count(subject="research rescope counter increments", equals=1)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget.rescoped`

### method: granted_review
- sig: `granted_review() -> Budget`
- does: returns a copy with lead_review_grants increased by one
- verify: count(subject="research lead-review grant increments", equals=1)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget.granted_review`

### method: granted_extension
- sig: `granted_extension() -> Budget`
- does: returns a copy with extension_grants increased by one
- verify: count(subject="research extension grant increments", equals=1)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget.granted_extension`

### method: reviewed
- sig: `reviewed() -> Budget`
- does: returns a copy with lead_reviews increased by one
- verify: count(subject="research lead-review counter increments", equals=1)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget.reviewed`

### method: extended
- sig: `extended() -> Budget`
- does: returns a copy with extensions increased by one
- verify: count(subject="research extension counter increments", equals=1)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget.extended`
