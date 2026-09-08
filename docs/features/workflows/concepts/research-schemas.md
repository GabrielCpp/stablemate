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
checkpoint value carrying all eight research counters and three operator grants.

- code: `workflows/src/workhorse_workflows/research/schemas.py`
- detail: [research workflow composition root](research-workflow-composition-root.md)

## Models

### method: ResearchResult
- sig: `ResearchResult(data: Any) -> ResearchResult`
- does: removes entries whose value is `None` from dictionary input before descendant validation
- verify: removed(subject="None-valued entries from dictionary input")
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
- sig: `Program(repo_dir: str = "", program: str = "", program_dir: str = "", progress_path: str = "", code_root: str = "", result_branch: str = "", goal: str = "", extensions_spent: int = 0, lead_reviews_spent: int = 0, program_reviews_spent: int = 0, recharters_spent: int = 0, status: str = "active", min_containment: str = "premium", envelope_ram_gb: int = 0, envelope_cpus: int = 0, envelope_gpu: str = "none", envelope_disk_gb: int = 0) -> Program`
- does: carries program paths, identity, ledger counters, status, and declared machine envelope
- verify: json_path(path="$.status", equals="active")
- verify: json_path(path="$.program_reviews_spent", equals=0)
- verify: json_path(path="$.recharters_spent", equals=0)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Program`

### method: Ledger
- sig: `Ledger(path: str = "", extensions: int = 0, lead_reviews: int = 0, program_reviews: int = 0, recharters: int = 0, status: str = "active") -> Ledger`
- does: carries the program-scoped counters and status written by spend recording
- verify: json_path(path="$.status", equals="active")
- verify: json_path(path="$.program_reviews", equals=0)
- verify: json_path(path="$.recharters", equals=0)
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
- does: carries the measurement argv
- verify: count(subject="the measurement argv", equals=0)
- does: carries the rehearsal argv
- verify: count(subject="the rehearsal argv", equals=0)
- does: carries the working directory
- verify: json_path(path="$.cwd", equals="")
- does: carries the result filename
- verify: json_path(path="$.result_file", equals="result.json")
- does: carries the code files
- verify: count(subject="the code files", equals=0)
- does: carries the fault locus
- verify: json_path(path="$.fault_locus", equals="")
- does: carries the component classification
- verify: json_path(path="$.component", equals="")
- code: `workflows/src/workhorse_workflows/research/schemas.py::Build`

### method: DryRun
- sig: `DryRun(ok: bool = false, exit_code: int | None = None, fault_locus: str = "", stderr_tail: str = "", reason: str = "") -> DryRun`
- does: reports rehearsal success
- verify: json_path(path="$.ok", equals=false)
- does: preserves the runner exit code
- verify: json_path(path="$.exit_code", equals=1)
- does: preserves the classified fault locus
- verify: json_path(path="$.fault_locus", equals="repo")
- does: preserves the captured stderr tail
- verify: json_path(path="$.stderr_tail", matches="Traceback")
- does: preserves the failure reason
- verify: json_path(path="$.reason", equals="no such file: run.py")
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

## Program-level evidence

### method: FrozenTarget
- sig: `FrozenTarget(metric: str = "", dataset: str = "", threshold: str = "", threshold_value: float = 0.0, threshold_count: int = 0, n: int = 0, seeds: list[int] = [], deadline: str = "", baseline_value: float = 0.0, baseline_count: int = 0, baseline_source: str = "") -> FrozenTarget`
- does: carries the parsed README `Frozen target` table as numbers
- does: holds raw threshold cell, threshold as fraction, threshold count from `N/D` form
- does: holds baseline value and count as fraction of `n`
- does: holds where baseline came from (`table`, `prose`, or empty)
- code: `workflows/src/workhorse_workflows/research/schemas.py::FrozenTarget`

### method: GateRow
- sig: `GateRow(gate_id: str = "", document: str = "", depends_on: str = "", status: str = "", result: str = "", date: str = "") -> GateRow`
- does: carries one row of a progress status table
- code: `workflows/src/workhorse_workflows/research/schemas.py::GateRow`

### method: HistoryEvent
- sig: `HistoryEvent(date: str = "", event: str = "", gate_id: str = "", note: str = "", source: str = "loop", fingerprint: str = "") -> HistoryEvent`
- does: carries one line of `history.jsonl` — what the loop did, when, to which gate
- does: `source` is `loop` for lines the workflow wrote, `bootstrap` for lines parsed from prose
- code: `workflows/src/workhorse_workflows/research/schemas.py::HistoryEvent`

### method: JobSummary
- sig: `JobSummary(gate_id: str = "", finished_at: str = "", exit_code: int = 0, wall_s: float = 0.0, kill_reason: str = "", n_completed: int = 0, n_planned: int = 0, seeds: list[int] = [], families: dict[str, list[float]] = {}, family_mean: dict[str, float] = {}, family_sd: dict[str, float] = {}, scalars: dict[str, float] = {}, flags: list[str] = []) -> JobSummary`
- does: carries what one `jobs/<gate>/` directory says, per seed family
- does: holds per-seed values extracted from `metrics` and their mean and SD
- does: holds scalar metrics that are not part of a seed family
- does: holds metric names whose value was truthy and whose name reads as a flag
- code: `workflows/src/workhorse_workflows/research/schemas.py::JobSummary`

### method: MetricPoint
- sig: `MetricPoint(date: str = "", value: float = 0.0, count: int = 0, n: int = 0, gate_id: str = "", source: str = "") -> MetricPoint`
- does: carries one dated observation of the frozen metric
- code: `workflows/src/workhorse_workflows/research/schemas.py::MetricPoint`

### method: Resolvability
- sig: `Resolvability(required_effect: float = 0.0, pooled_se: float = 0.0, per_seed_required: float = 0.0, per_seed_se: float = 0.0, observed_seed_sd: float = 0.0, ratio: float = 0.0, resolvable: bool = False, statement: str = "") -> Resolvability`
- does: carries whether the frozen target's effect can be told from seed noise on its own eval
- does: holds pooled binomial SE at baseline rate over `n`
- does: holds per-seed required tasks and SE when seeds are known
- does: holds observed per-seed spread when a seed family for the metric exists
- does: holds ratio of required effect to per-seed SE and resolvability verdict
- code: `workflows/src/workhorse_workflows/research/schemas.py::Resolvability`

### method: Dossier
- sig: `Dossier(today: str = "", program_dir: str = "", frozen: FrozenTarget = FrozenTarget(), rows: list[GateRow] = [], superseded_rows: list[GateRow] = [], history: list[HistoryEvent] = [], jobs: list[JobSummary] = [], series: list[MetricPoint] = [], moved_last_on: str = "", days_since_moved: int = 0, days_to_deadline: int = 0, resolvability: Resolvability = Resolvability(), counts: dict[str, int] = {}, churn: dict[str, int] = {}, pending: list[str] = [], triggers: list[str] = [], circling: bool = False, fingerprint: str = "", review_due: bool = False, active_gate: str = "", unparsed: list[str] = []) -> Dossier`
- does: carries the computed program-level evidence one `program_review` turn is judged on
- verify: json_path(path="$.today", equals="")
- does: holds frozen target, gate ladder rows, history events, job summaries, metric series
- verify: json_path(path="$.frozen.metric", equals="")
- verify: count(subject="gate ladder rows", equals=0)
- verify: count(subject="history events", equals=0)
- verify: count(subject="job summaries", equals=0)
- verify: count(subject="metric series", equals=0)
- does: holds days-since-last-metric-move and days-to-deadline
- verify: json_path(path="$.days_since_moved", equals=0)
- verify: json_path(path="$.days_to_deadline", equals=0)
- does: holds per-seed resolvability assessment and code churn per gate
- verify: json_path(path="$.resolvability.resolvable", equals=false)
- verify: count(subject="code churn per gate", equals=0)
- does: holds pending results, circling triggers, and circling verdict
- verify: count(subject="pending results", equals=0)
- verify: count(subject="circling triggers", equals=0)
- verify: json_path(path="$.circling", equals=false)
- does: holds parse-failure reports in `unparsed`
- verify: count(subject="parse-failure reports", equals=0)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Dossier`

### method: ProbeOrder
- sig: `ProbeOrder(gate_id: str = "", question: str = "", expected_cost_s: int = 0, kill_if: str = "") -> ProbeOrder`
- does: carries a cheap, decisive measurement the lead orders before any more gate work
- code: `workflows/src/workhorse_workflows/research/schemas.py::ProbeOrder`

### method: NewTarget
- sig: `NewTarget(metric: str = "", dataset: str = "", threshold: str = "", threshold_count: int = 0, n: int = 0, seeds: list[int] = [], baseline: str = "", baseline_count: int = 0, deadline: str = "", why_resolvable: str = "") -> NewTarget`
- does: carries a re-chartered frozen target
- does: `why_resolvable` is checked in code, not trusted from agent
- code: `workflows/src/workhorse_workflows/research/schemas.py::NewTarget`

### method: ProgramReview
- sig: `ProgramReview(verdict: str = "", circling: bool = False, triggers_confirmed: list[str] = [], reason: str = "", evidence: list[str] = [], probe: ProbeOrder = ProbeOrder(), cache_gate_id: str = "", cache_dir: str = "", recharter: NewTarget = NewTarget(), operator_question: str = "", confidence: str = "") -> ProgramReview`
- does: carries the lead's program-level verdict on a dossier
- does: `verdict` is one of `continue`, `probe_first`, `score_from_cache`, `recharter`, `bank`, `stop_negative`, `operator`
- does: default `""` matches no arm and parks
- code: `workflows/src/workhorse_workflows/research/schemas.py::ProgramReview`

### method: RecharterResult
- sig: `RecharterResult(status: str = "", new_target: NewTarget = NewTarget(), probe_doc_path: str = "", cache_doc_path: str = "", readme_path: str = "", progress_updated: bool = False, reason: str = "") -> RecharterResult`
- does: carries what `program-recharter` wrote into the program folder
- code: `workflows/src/workhorse_workflows/research/schemas.py::RecharterResult`

## Budget

### method: Budget
- sig: `Budget(reworks: int = 0, build_fixes: int = 0, rescopes: int = 0, lead_reviews: int = 0, extensions: int = 0, program_reviews: int = 0, recharters: int = 0, gate_cycles: int = 0, lead_review_grants: int = 0, extension_grants: int = 0, program_review_grants: int = 0) -> Budget`
- does: carries per-gate rework, build-fix, and rescope counters
- verify: json_path(path="$.reworks", equals=0)
- does: carries run-wide review, extension, program-review, and recharter counters
- verify: json_path(path="$.lead_reviews", equals=0)
- verify: json_path(path="$.program_reviews", equals=0)
- verify: json_path(path="$.recharters", equals=0)
- does: carries a gate-cycle counter that resets each periodic program review
- verify: json_path(path="$.gate_cycles", equals=0)
- does: carries operator lead-review, extension, and program-review grants
- verify: json_path(path="$.lead_review_grants", equals=0)
- verify: json_path(path="$.program_review_grants", equals=0)
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

### method: cycled
- sig: `cycled() -> Budget`
- does: returns a copy with gate_cycles increased by one
- verify: count(subject="research gate-cycle counter increments", equals=1)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget.cycled`

### method: program_reviewed
- sig: `program_reviewed() -> Budget`
- does: returns a copy with program_reviews increased by one
- verify: count(subject="research program-review counter increments", equals=1)
- does: returns a copy with gate_cycles reset to zero
- verify: count(subject="research gate-cycle counter resets on program review", equals=1)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget.program_reviewed`

### method: rechartered
- sig: `rechartered() -> Budget`
- does: returns a copy with recharters increased by one
- verify: count(subject="research recharter counter increments", equals=1)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget.rechartered`

### method: granted_program_review
- sig: `granted_program_review() -> Budget`
- does: returns a copy with program_review_grants increased by one
- verify: count(subject="research program-review grant increments", equals=1)
- code: `workflows/src/workhorse_workflows/research/schemas.py::Budget.granted_program_review`
