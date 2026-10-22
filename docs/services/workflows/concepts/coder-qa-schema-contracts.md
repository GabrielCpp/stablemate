---
type: concept
slug: coder-qa-schema-contracts
title: Coder QA schema contracts
---
# Coder QA schema contracts

The `coder.shared.schemas.qa` module is the typed boundary for the QA flow. It keeps the rolling
verdict separate from agent-turn replies and keeps deterministic plan and stack results pessimistic. `QaResult.status` is
`passed | failed | blocked | invalid`; plan validation is `passed | invalid`; regression has
the additional `skipped` and `error` states documented by the [regression contract](coder-qa-regression.md).
One owner turn replies with `QaOwnerResult`, and the flow ends with `QaFlowResult`, whose status is
`passed | replan | refix`. The exported `QaFlowStatus` and `QaStatus` aliases close the routing
vocabularies rather than accepting arbitrary strings. `QaResult`, `QaPlanRun`, `StackStatus` and `QaStatus`
are defined in the shared QA kit and re-exported here.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::__all__` @ae2e8b0c6330
- tests: `workflows/tests/coder/qa/test_flow.py::test_one_clean_pass_spends_one_owner_turn`
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
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/kit/qa/schemas.py::QaResult` @ce51b75fe700

### method: QaPlanRun
- sig: `QaPlanRun(status: QaStatus | Literal[""] = "", notes: str = "", ostler: dict[str, Any] = {}) -> QaPlanRun`
- does: carries a `QaResult` verdict together with the raw Ostler runner payload
- verify: json_path(path="$.ostler.overall", matches="^(Pass|Fail|Blocked|Invalid)$")
- returns: a result whose runner-only payload is not required of agent-turn `QaResult` values
- verify: json_path(path="$.status", matches="^(|passed|failed|blocked|invalid)$")
- code: `workflows/src/workhorse_workflows/kit/qa/schemas.py::QaPlanRun` @ce51b75fe700

### method: QaRunResult
- sig: `QaRunResult(status: Literal["passed", "failed", "blocked"], notes: str = "") -> QaRunResult`
- does: requires an agent turn to report whether its QA fix check passed, failed, or was blocked
- verify: json_path(path="$.status", matches="^(passed|failed|blocked)$")
- returns: the turn's notes describing exercised commands, changed files, and remaining defect or dependency
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaRunResult` @ae2e8b0c6330

### method: QaPlanValidation
- sig: `QaPlanValidation(status: Literal["passed", "invalid"] = "invalid", notes: str = "", ostler: dict[str, Any] = {}) -> QaPlanValidation`
- does: records whether `ostler qa validate` found the authored QA plan executable
- verify: json_path(path="$.status", equals="invalid")
- returns: a validation result with notes and the validator payload, defaulting conservatively to invalid
- verify: json_path(path="$.ostler", equals="{}")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaPlanValidation` @ae2e8b0c6330

### method: DryRunGate
- sig: `DryRunGate(status: Literal["passed", "failed"] = "failed", notes: str = "", scenarios: list[str] = [], verified: list[str] = []) -> DryRunGate`
- does: records the scenarios demanded by a plan repair or draft and the scenarios proved by scratch evidence
- verify: json_path(path="$.scenarios", matches="^\\[\"[^\"]+\"")
- returns: a failed-by-default gate unless every demanded dry-run condition is later established
- verify: json_path(path="$.status", equals="failed")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::DryRunGate` @ae2e8b0c6330

### method: QaToolCatalog
- sig: `QaToolCatalog(tools: list[dict[str, Any]] = [], errors: list[str] = []) -> QaToolCatalog`
- does: checkpoints the configured QA tools and their host-resolution errors
- verify: json_path(path="$.tools", equals="[]")
- returns: a catalog that is not re-derived from the host on resume
- verify: json_path(path="$.errors", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaToolCatalog` @ae2e8b0c6330

### method: QaCleared
- sig: `QaCleared(cleared: bool = False) -> QaCleared`
- does: reports whether stale QA artifacts and the root verdict were cleared
- verify: json_path(path="$.cleared", matches="^(true|false)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaCleared` @ae2e8b0c6330

### method: StackStatus
- sig: `StackStatus(ready: Literal["yes", "no", "none", "unneeded"] = "no", app_pid: str = "", app_pgid: str = "", entry_url: str = "", failed_step: str = "", notes: str = "", owned_pgids: tuple[str, ...] = (), app_logs: tuple[str, ...] = ()) -> StackStatus`
- does: classifies the QA stack as ready, broken, undeclared, or correctly unnecessary
- verify: json_path(path="$.ready", matches="^(yes|no|none|unneeded)$")
- returns: string process identifiers, the process groups the bring-up owns, the application log paths and diagnostics for the owner to repair the stack from
- verify: json_path(path="$.app_pid", equals="CASE-1234")
- code: `workflows/src/workhorse_workflows/kit/qa/schemas.py::StackStatus` @ce51b75fe700

### method: StackTornDown
- sig: `StackTornDown(torn_down: Literal["yes", "no", "skipped"] = "no", notes: str = "") -> StackTornDown`
- does: records whether the run-owned stack was torn down or teardown was skipped because no stop recipe exists
- verify: json_path(path="$.torn_down", matches="^(yes|no|skipped)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::StackTornDown` @ae2e8b0c6330

### method: BacklogDrain
- sig: `BacklogDrain(appended: int = 0, skipped: int = 0, notes: str = "") -> BacklogDrain`
- does: reports appended and skipped coder-to-author backlog items without routing the story on either count
- verify: json_path(path="$.appended", matches="^[0-9]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::BacklogDrain` @ae2e8b0c6330

### method: ScreenshotFlush
- sig: `ScreenshotFlush(flushed: int = 0, kept_tracked: int = 0, notes: str = "") -> ScreenshotFlush`
- does: reports root screenshots moved into QA storage and tracked images deliberately retained
- verify: json_path(path="$.flushed", matches="^[0-9]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::ScreenshotFlush` @ae2e8b0c6330

### method: RegressionSuite
- sig: `RegressionSuite(label: str = "", cwd: str = "", command: str = "") -> RegressionSuite`
- does: identifies one configured regression command by service label, absolute working directory, and command text
- verify: json_path(path="$.command", equals="make test")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::RegressionSuite` @ae2e8b0c6330

### method: RegressionSuites
- sig: `RegressionSuites(suites: list[RegressionSuite] = []) -> RegressionSuites`
- does: carries every resolved regression suite selected by the current QA plan
- verify: json_path(path="$.suites[0].command", equals="run-journeys")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::RegressionSuites` @ae2e8b0c6330

### method: FailureAttribution
- sig: `FailureAttribution(test: str = "", path: str = "", classification: Literal["impacted", "outside-impact", "unattributed"] = "unattributed", nodes: list[str] = []) -> FailureAttribution`
- does: records the verification-index ownership classification for one failed regression test without changing its verdict
- verify: json_path(path="$.classification", matches="^(impacted|outside-impact|unattributed)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::FailureAttribution` @ae2e8b0c6330

### method: RegressionRun
- sig: `RegressionRun(status: Literal["passed", "failed", "blocked", "skipped", "error"] = "skipped", failing_tests: list[str] = [], log_path: str = "", notes: str = "", failure_attribution: list[FailureAttribution] = []) -> RegressionRun`
- does: carries the regression suite verdict, failing tests, retained log path, notes, and optional attribution
- verify: json_path(path="$.status", matches="^(passed|failed|blocked|skipped|error)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::RegressionRun` @ae2e8b0c6330

### method: QaFinding
- sig: `QaFinding(id: str = "", target: str = "", issue: str = "", repair: str = "") -> QaFinding`
- does: identifies one product defect the scored run proved, with a stable handle the owner reuses when it restates the finding
- verify: json_path(path="$.id", equals="login-redirect")
- returns: an actionable finding only when both target and repair are present
- verify: json_path(path="$.target", equals="src/app.py")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaFinding` @ae2e8b0c6330

### method: QaOwnerResult
- sig: `QaOwnerResult(status: Literal["passed", "findings", "blocked"], notes: str = "", findings: list[QaFinding] = [], proved_scenarios: list[str] = []) -> QaOwnerResult`
- does: reports the QA owner turn's verdict on its story
- verify: json_path(path="$.status", matches="^(passed|findings|blocked)$")
- does: names the product defects the scored run proved, one finding each, and leaves the list empty on a pass or a block
- verify: json_path(path="$.findings", equals="[]")
- does: names every scenario the turn added or changed and dry-ran green, which the dry-run gate checks against the scratch logs
- verify: json_path(path="$.proved_scenarios[0]", equals="login-happy-path")
- returns: a reply whose `blocked` status is reserved for what only an operator can decide, since a plan, stack or setup problem is the owner's to repair
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaOwnerResult` @ae2e8b0c6330

### method: StackTarget
- sig: `StackTarget(near: str = "", lease: str = "", env: dict[str, str] = {}) -> StackTarget`
- does: names the book whose stack a story's QA runs against, the lease the run holds a copy of it with, and the environment that stack selects
- verify: json_path(path="$.near", equals="docs/services/app")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::StackTarget` @ae2e8b0c6330

### method: QaFlowResult
- sig: `QaFlowResult(status: QaFlowStatus = "passed", qa: QaResult = QaResult(), operator_notes: str = "", docs_recheck_required: bool = True, findings: list[QaFinding] = []) -> QaFlowResult`
- does: returns the QA flow's terminal routing status, verdict, operator notes, docs-recheck taint and the findings the dev owner fixes
- verify: json_path(path="$.status", matches="^(passed|replan|refix)$")
- does: carries the findings of a `refix` result to the dev owner, and of a development-target pass to the tracker report
- verify: json_path(path="$.findings", equals="[]")
- does: defaults `docs_recheck_required` to `True` so a terminal result cannot imply the documentation story has stayed clean without an explicit False
- verify: json_path(path="$.docs_recheck_required", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaFlowResult` @ae2e8b0c6330
- tests: `workflows/tests/coder/test_telemetry.py::test_missing_documentation_taint_fails_closed`
