---
type: concept
slug: coder-qa-schema-contracts
title: Coder QA schema contracts
---
# Coder QA schema contracts

The `coder.shared.schemas.qa` module is the typed boundary for the QA flow. It keeps the rolling
verdict separate from agent-turn replies, keeps deterministic plan and stack results pessimistic,
and carries all repair diagnostics through checkpoint/resume. `QaResult.status` is
`passed | failed | blocked | invalid`; plan validation is `passed | invalid`; regression has
the additional `skipped` and `error` states documented by the [regression contract](coder-qa-regression.md).
The exported `QaDisposition`, `QaFailureClass`, `QaAuditVerdict`, `QaRefutationClass`,
`QaTriageAction`, `QaTriageClass`, `QaFlowStatus`, and `QaStatus` aliases close the routing
vocabularies rather than accepting arbitrary strings.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::__all__`
- tests: `workflows/tests/coder/qa/test_flow.py::test_one_clean_pass_through_every_gate`
- tests: `workflows/tests/coder/test_qa_plan_prompt_schema.py::test_the_example_scenario_would_survive_the_substantiveness_gate`
- detail: [coder QA flow](../flows/coder-qa.md)
- detail: [coder QA regression suites](coder-qa-regression.md)
- detail: [coder QA node operations](qa-node-operations.md)

The models below are Pydantic values that ignore unknown keys and drop null inputs through
`CoderResult`; fields not otherwise marked therefore retain the defaults shown here when a
Python-produced node emits no result. Agent-produced statuses without defaults remain required,
so an omitted decision is retried rather than silently routed.

## Models

### method: QaResult
- sig: `QaResult(status: QaStatus | Literal[""] = "", notes: str = "") -> QaResult`
- does: carries the rolling QA verdict and one-line routing notes, starting blank before any gate runs
- verify: json_path(path="$.status", equals="")
- returns: a four-state QA result whose blank status is distinct from `invalid`
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaResult`

### method: QaPlanRun
- sig: `QaPlanRun(status: QaStatus | Literal[""] = "", notes: str = "", ostler: dict[str, Any] = {}) -> QaPlanRun`
- does: carries a `QaResult` verdict together with the raw Ostler runner payload
- verify: json_path(path="$.ostler.overall", matches="^(Pass|Fail|Blocked|Invalid)$")
- returns: a result whose runner-only payload is not required of agent-turn `QaResult` values
- verify: json_path(path="$.status", matches="^(|passed|failed|blocked|invalid)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaPlanRun`

### method: QaRunResult
- sig: `QaRunResult(status: Literal["passed", "failed", "blocked"], notes: str = "") -> QaRunResult`
- does: requires an agent turn to report whether its QA fix check passed, failed, or was blocked
- verify: json_path(path="$.status", matches="^(passed|failed|blocked)$")
- returns: the turn's notes describing exercised commands, changed files, and remaining defect or dependency
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaRunResult`

### method: QaPlanValidation
- sig: `QaPlanValidation(status: Literal["passed", "invalid"] = "invalid", notes: str = "", ostler: dict[str, Any] = {}) -> QaPlanValidation`
- does: records whether `ostler qa validate` found the authored QA plan executable
- verify: json_path(path="$.status", equals="invalid")
- returns: a validation result with notes and the validator payload, defaulting conservatively to invalid
- verify: json_path(path="$.ostler", equals="{}")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaPlanValidation`

### method: DryRunGate
- sig: `DryRunGate(status: Literal["passed", "failed"] = "failed", notes: str = "", scenarios: list[str] = [], verified: list[str] = []) -> DryRunGate`
- does: records the scenarios demanded by a plan repair or draft and the scenarios proved by scratch evidence
- verify: json_path(path="$.scenarios", matches="^\\['[^']+'")
- returns: a failed-by-default gate unless every demanded dry-run condition is later established
- verify: json_path(path="$.status", equals="failed")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::DryRunGate`

### method: QaToolCatalog
- sig: `QaToolCatalog(tools: list[dict[str, Any]] = [], errors: list[str] = []) -> QaToolCatalog`
- does: checkpoints the configured QA tools and their host-resolution errors
- verify: json_path(path="$.tools", equals="[]")
- returns: a catalog that is not re-derived from the host on resume
- verify: json_path(path="$.errors", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaToolCatalog`

### method: QaCleared
- sig: `QaCleared(cleared: bool = False) -> QaCleared`
- does: reports whether stale QA artifacts and the root verdict were cleared
- verify: json_path(path="$.cleared", matches="^(true|false)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaCleared`

### method: StackStatus
- sig: `StackStatus(ready: Literal["yes", "no", "none", "unneeded"] = "no", app_pid: str = "", app_pgid: str = "", entry_url: str = "", failed_step: str = "", notes: str = "") -> StackStatus`
- does: classifies the QA stack as ready, broken, undeclared, or correctly unnecessary
- verify: json_path(path="$.ready", matches="^(yes|no|none|unneeded)$")
- returns: string process identifiers and diagnostics for the stack setup loop
- verify: json_path(path="$.app_pid", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::StackStatus`

### method: StackTornDown
- sig: `StackTornDown(torn_down: Literal["yes", "no", "skipped"] = "no", notes: str = "") -> StackTornDown`
- does: records whether the run-owned stack was torn down or teardown was skipped because no stop recipe exists
- verify: json_path(path="$.torn_down", matches="^(yes|no|skipped)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::StackTornDown`

### method: BacklogDrain
- sig: `BacklogDrain(appended: int = 0, skipped: int = 0, notes: str = "") -> BacklogDrain`
- does: reports appended and skipped coder-to-author backlog items without routing the story on either count
- verify: json_path(path="$.appended", matches="^[0-9]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::BacklogDrain`

### method: ScreenshotFlush
- sig: `ScreenshotFlush(flushed: int = 0, kept_tracked: int = 0, notes: str = "") -> ScreenshotFlush`
- does: reports root screenshots moved into QA storage and tracked images deliberately retained
- verify: json_path(path="$.flushed", matches="^[0-9]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::ScreenshotFlush`

### method: RegressionSuite
- sig: `RegressionSuite(label: str = "", cwd: str = "", command: str = "") -> RegressionSuite`
- does: identifies one configured regression command by service label, absolute working directory, and command text
- verify: json_path(path="$.command", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::RegressionSuite`

### method: RegressionSuites
- sig: `RegressionSuites(suites: list[RegressionSuite] = []) -> RegressionSuites`
- does: carries every resolved regression suite selected by the current QA plan
- verify: json_path(path="$.suites", absent=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::RegressionSuites`

### method: FailureAttribution
- sig: `FailureAttribution(test: str = "", path: str = "", classification: Literal["impacted", "outside-impact", "unattributed"] = "unattributed", nodes: list[str] = []) -> FailureAttribution`
- does: records the verification-index ownership classification for one failed regression test without changing its verdict
- verify: json_path(path="$.classification", matches="^(impacted|outside-impact|unattributed)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::FailureAttribution`

### method: RegressionRun
- sig: `RegressionRun(status: Literal["passed", "failed", "blocked", "skipped", "error"] = "skipped", failing_tests: list[str] = [], log_path: str = "", notes: str = "", failure_attribution: list[FailureAttribution] = []) -> RegressionRun`
- does: carries the regression suite verdict, failing tests, retained log path, notes, and optional attribution
- verify: json_path(path="$.status", matches="^(passed|failed|blocked|skipped|error)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::RegressionRun`

### method: ContextRepair
- sig: `ContextRepair(status: Literal["repaired", "blocked"], notes: str = "") -> ContextRepair`
- does: reports that QA context was repaired or that an external decision/dependency blocks repair
- verify: json_path(path="$.status", matches="^(repaired|blocked)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::ContextRepair`

### method: QaPlanResult
- sig: `QaPlanResult(status: Literal["done", "blocked"], notes: str = "", repaired_scenarios: list[str] = [], proved_scenarios: list[str] = []) -> QaPlanResult`
- does: reports an authored or repaired plan and names scenarios changed or dry-run proved by that turn
- verify: json_path(path="$.status", matches="^(done|blocked)$")
- returns: a plan result whose scenario lists are claims consumed by the dry-run gate
- verify: json_path(path="$.repaired_scenarios", matches="^\\[(?:'[^']+'(?:, )?)*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaPlanResult`

### method: QaFinding
- sig: `QaFinding(id: str = "", scope: Literal["plan", "stack", "product-test"] = "plan", kind: Literal["coverage", "overclaim", "cosmetic"] = "coverage", target: str = "", issue: str = "", repair: str = "") -> QaFinding`
- does: identifies one QA defect, its repair location, its defect kind, and the owner that can act on it
- verify: json_path(path="$.scope", matches="^(plan|stack|product-test)$")
- returns: an actionable finding only when both target and repair are present
- verify: json_path(path="$.target", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaFinding`

### method: QaAssessment
- sig: `QaAssessment(status: Literal["assessed", "blocked"], disposition: QaDisposition | None = None, failure_class: QaFailureClass | None = None, objective_reached: bool | None = None, findings: list[QaFinding] = [], notes: str = "QA run assessment produced no valid result.") -> QaAssessment`
- does: classifies a readable QA run as confirmed, repairable, or blocked and routes findings by owner
- verify: json_path(path="$.status", matches="^(assessed|blocked)$")
- returns: an assessed result with disposition, failure class, objective outcome, findings, and notes, or null classification on block
- verify: json_path(path="$.findings", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaAssessment`

### method: QaAudit
- sig: `QaAudit(status: Literal["audited", "blocked"], verdict: QaAuditVerdict | None = None, refutation_class: QaRefutationClass | None = None, findings: list[QaFinding] = [], notes: str = "Independent QA audit produced no valid result.") -> QaAudit`
- does: records the adversarial audit verdict and routes any refutation to its repair owner
- verify: json_path(path="$.status", matches="^(audited|blocked)$")
- returns: an audited result with `stands` or `refuted`, with no verdict classification on block
- verify: json_path(path="$.findings", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaAudit`

### method: QaTriage
- sig: `QaTriage(status: Literal["triaged", "blocked"], triage_action: QaTriageAction | None = None, qa_failure_class: QaTriageClass | None = None, notes: str = "") -> QaTriage`
- does: sorts QA findings into rescope or QA-fix work and classifies the remaining owner
- verify: json_path(path="$.status", matches="^(triaged|blocked)$")
- returns: a triage decision with no classification when the findings could not be sorted
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaTriage`

### method: QaReport
- sig: `QaReport(status: Literal["reported", "blocked"], notes: str = "") -> QaReport`
- does: reports that the development-target QA comment was written or explains why it could not be written
- verify: json_path(path="$.status", matches="^(reported|blocked)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaReport`

### method: RegressionFix
- sig: `RegressionFix(status: Literal["attempted", "blocked"], notes: str = "") -> RegressionFix`
- does: records that regression repair work was attempted without treating the agent's claim as a passing verdict
- verify: json_path(path="$.status", matches="^(attempted|blocked)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::RegressionFix`

### method: SetupResult
- sig: `SetupResult(status: Literal["ready", "unfixable"], notes: str = "") -> SetupResult`
- does: reports that QA setup is runnable or that a human-only environment dependency remains
- verify: json_path(path="$.status", matches="^(ready|unfixable)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::SetupResult`

### method: AssessmentRecord
- sig: `AssessmentRecord(notes: str = "", disposition: QaDisposition | Literal[""] = "", failure_class: QaFailureClass | Literal[""] = "") -> AssessmentRecord`
- does: checkpoints the latest execution-assessment notes and classifications, blank until that gate runs
- verify: json_path(path="$.disposition", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::AssessmentRecord`

### method: AuditRecord
- sig: `AuditRecord(notes: str = "", verdict: QaAuditVerdict | Literal[""] = "", refutation_class: QaRefutationClass | Literal[""] = "") -> AuditRecord`
- does: checkpoints the latest independent-audit notes and classifications, blank until that gate runs
- verify: json_path(path="$.verdict", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::AuditRecord`

### method: FixWorklist
- sig: `FixWorklist(items: tuple[str, ...] = (), rework: int = 0, problems: tuple[str, ...] = ()) -> FixWorklist`
- does: checkpoints the remaining scenario ids, head rework count, and ordered dry-run refusals
- verify: json_path(path="$.items", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::FixWorklist`

### method: LaneClock
- sig: `LaneClock(seconds: float = 0.0, plan_seconds: float = 0.0, chain_laps: int = 0, overruns: int = 0) -> LaneClock`
- does: accumulates charged turn deltas for the QA and plan lanes and counts plan-chain overruns
- verify: json_path(path="$.seconds", equals=0.0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::LaneClock`

### method: QaLoop
- sig: `QaLoop(qa: QaResult = QaResult(), context_status: Literal["", "passed", "invalid"] = "", context_notes: str = "", plan_validation_notes: str = "", assessment: AssessmentRecord = AssessmentRecord(), audit: AuditRecord = AuditRecord(), failure_class: QaTriageClass | Literal[""] = "", context_rework: int = 0, plan_rework: int = 0, plan_validation_rework: int = 0, qa_rework: int = 0, setup_rework: int = 0, regression_fix: int = 0, audit_rework: int = 0, blocked_problems: tuple[str, ...] = (), setup_problems: tuple[str, ...] = (), fix: FixWorklist = FixWorklist(), plan_rejections: tuple[str, ...] = (), repaired_failures: tuple[str, ...] = (), repaired_lap: str = "", tried_laps: tuple[str, ...] = (), class_switched: bool = False, escalations: int = 0, triage_scope: int = 0, regression_fix_applied: bool = False, regression_reqa_pending: bool = False, bonus_used: bool = False, docs_recheck_required: bool = True, clock: LaneClock = LaneClock()) -> QaLoop`
- does: carries verdicts, diagnostics, repair budgets, fingerprints, worklists, escalation state, regression flags, docs taint, and clocks as one resumable QA state
- verify: json_path(path="$.docs_recheck_required", equals=true)
- returns: a fail-closed loop with blank gate records, zero counters, empty worklists, and a blank running verdict
- verify: json_path(path="$.qa.status", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaLoop`

### method: QaFlowResult
- sig: `QaFlowResult(status: QaFlowStatus = "inconclusive", qa: QaResult = QaResult(), qa_rework: int = 0, triage_scope: int = 0, operator_notes: str = "", docs_recheck_required: bool = True) -> QaFlowResult`
- does: returns the QA flow's terminal routing status, verdict, rework count, triage scope, operator notes, and docs-recheck taint
- verify: json_path(path="$.status", matches="^(passed|inconclusive|replan|rescope|refix)$")
- returns: an inconclusive-by-default result that cannot imply a passing QA flow
- verify: json_path(path="$.status", equals="inconclusive")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaFlowResult`

## Methods

### ContextRepair.as_qa_result
- sig: `ContextRepair.as_qa_result(self) -> QaResult`
- does: maps a repaired context to `invalid` while it is rebuilt and a blocked repair to `blocked`
- verify: json_path(path="$.status", matches="^(invalid|blocked)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::ContextRepair.as_qa_result`

### AssessmentRecord.dimensions
- sig: `AssessmentRecord.dimensions(self) -> dict[str, str]`
- does: exposes disposition and failure class under telemetry names ending in `_disposition` and `_failure_class`
- verify: json_path(path="$.assessment_disposition", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::AssessmentRecord.dimensions`

### AuditRecord.dimensions
- sig: `AuditRecord.dimensions(self) -> dict[str, str]`
- does: exposes audit verdict and refutation class under telemetry classification names
- verify: json_path(path="$.audit_verdict", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::AuditRecord.dimensions`

### FixWorklist.popped
- sig: `FixWorklist.popped(self) -> FixWorklist`
- does: removes the proved head scenario and resets the remaining worklist's per-head rework and problem state
- verify: json_path(path="$.items", equals=[])
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::FixWorklist.popped`

### LaneClock.charged
- sig: `LaneClock.charged(self, seconds: float, *, plan: bool, overran: bool = False) -> LaneClock`
- does: returns a new `LaneClock` with one turn's elapsed delta added to total seconds, optionally to plan seconds, and optionally to overrun count
- verify: created(subject="a new charged LaneClock")
- verify: json_path(path="$.seconds", matches="^[0-9.]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::LaneClock.charged`

### QaLoop.plan_rework_total
- sig: `QaLoop.plan_rework_total -> int`
- returns: the sum of plan semantic and plan-validation rework counters used by the outer plan ceiling
- verify: json_path(path="$.plan_rework_total", matches="^[0-9]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaLoop.plan_rework_total`

### QaLoop.plan_judgement_rework
- sig: `QaLoop.plan_judgement_rework -> int`
- returns: the semantic plan-rework counter excluding mechanical validation repairs
- verify: json_path(path="$.plan_judgement_rework", matches="^[0-9]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaLoop.plan_judgement_rework`

### QaLoop.update
- sig: `QaLoop.update(self, **changes: object) -> QaLoop`
- does: returns a copy of the loop with the named fields replaced
- verify: json_path(path="$.qa", absent=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaLoop.update`

### QaLoop.with_qa
- sig: `QaLoop.with_qa(self, qa: QaResult) -> QaLoop`
- does: returns a copy carrying a new rolling QA verdict
- verify: json_path(path="$.qa.status", equals="failed")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaLoop.with_qa`

### QaLoop.with_lap
- sig: `QaLoop.with_lap(self, lap: str, **changes: object) -> QaLoop`
- does: records the latest repair class and adds it once to the tried-lap fingerprint
- verify: json_path(path="$.tried_laps", equals=["code fix"])
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaLoop.with_lap`

### QaLoop.charged
- sig: `QaLoop.charged(self, seconds: float, *, plan: bool = False, overran: bool = False) -> QaLoop`
- does: returns a copy whose lane clock includes one turn's charged delta and optional overrun
- verify: json_path(path="$.clock.seconds", equals=1.5)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaLoop.charged`

### QaLoop.require_docs_recheck
- sig: `QaLoop.require_docs_recheck(self) -> QaLoop`
- does: sets the documentation-recheck taint without clearing it during later loop transitions
- verify: json_path(path="$.docs_recheck_required", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaLoop.require_docs_recheck`

### QaLoop.cleared
- sig: `QaLoop.cleared(self) -> QaLoop`
- does: blanks the running verdict and gate diagnostics while retaining context status and all durable budgets
- verify: json_path(path="$.qa.status", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaLoop.cleared`

### QaLoop.block_notes
- sig: `QaLoop.block_notes -> str`
- returns: the current QA and assessment notes joined into the brief sent to setup repair and operator resolution
- verify: json_path(path="$.block_notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaLoop.block_notes`
