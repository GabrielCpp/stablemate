---
type: concept
slug: qa-evidence-gate
title: QA evidence gate
---
# QA evidence gate

The evidence gate is the fail-closed boundary after the QA runner claims `passed`. It never
upgrades a verdict: `failed`, `blocked`, and `invalid` pass through, while a malformed or
incomplete claimed pass becomes `invalid` so the flow repairs its proof rather than treating a
product failure as actionable code work. All independent findings are accumulated in one result.
The gate is part of the [Coder QA subflow](coder-qa-subflow.md) and is reached by the
[evidence-and-audit stage](../flows/coder-qa.md#evidence-and-audit).

- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py`
- detail: [coder QA subflow](coder-qa-subflow.md)

## Fields

### EVIDENCE_FILE
- type: `str`
- default: `qa-evidence.json`
- required: true
- semantics: specification-relative JSON artifact containing the runner's criteria, obligations, run identity, and evidence references
- verify: json_path(path="$.EVIDENCE_FILE", equals="qa-evidence.json")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::EVIDENCE_FILE`

### REPORT
- type: `str`
- default: `REPORT_FILE`
- required: true
- semantics: specification-relative reviewer report that must carry the same run marker as the evidence artifact
- verify: json_path(path="$.REPORT", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::REPORT`

### PASSTHROUGH_STATUSES
- type: `dict[str, QaStatus]`
- default: `failed -> failed, blocked -> blocked, invalid -> invalid`
- required: true
- semantics: closed mapping for non-pass runner claims
- verify: count(subject="preserved non-pass QA statuses", equals=3)
- semantics: an empty or unknown claim is not mapped and becomes invalid
- verify: json_path(path="$.status", equals="invalid")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::PASSTHROUGH_STATUSES`

### CRITERION_KINDS
- type: `tuple[str, ...]`
- default: `behavioral, parity, data-entry, transient`
- required: true
- semantics: criterion proof modes, each of which adds its own evidence obligation to a claimed pass
- verify: count(subject="accepted QA criterion kinds", equals=4)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::CRITERION_KINDS`

## Methods

### _run_log_tally
- sig: `_run_log_tally(spec_dir: Path) -> tuple[int, int]`
- does: counts PASS assertion records in `qa/qa-run.ndjson` as the first result and FAIL assertion records as the second
- verify: json_path(path="$.tally", matches=".+")
- does: returns `(0, 0)` when the log is absent, empty, malformed, or contains no assertion records
- verify: json_path(path="$.tally", equals="(0, 0)")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::_run_log_tally`

### _exists
- sig: `_exists(ref: Any, root: Path, spec_dir: Path) -> bool`
- does: rejects an empty evidence reference
- verify: count(subject="empty evidence references rejected", equals=1)
- does: accepts a file reference when it resolves as an absolute path, repository-relative path, specification-relative path, or specification-parent-relative path
- verify: count(subject="evidence reference roots", equals=4)
- returns: true only when one candidate is an existing file
- verify: json_path(path="$.exists", equals=true)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::_exists`

### _artifact_problems
- sig: `_artifact_problems(spec_dir: Path, data: dict) -> tuple[list[str], dict, dict]`
- does: requires a non-empty QA plan
- verify: count(subject="non-empty QA plans", equals=1)
- does: requires `qa-okf-context.json` to be a JSON object
- verify: count(subject="JSON-object QA contexts", equals=1)
- does: requires a non-empty `qa/qa-run.ndjson`
- verify: count(subject="non-empty QA run logs", equals=1)
- does: requires `qa/run-manifest.json` to be a JSON object
- verify: count(subject="JSON-object QA run manifests", equals=1)
- does: requires `qa-evidence.json` to identify `qa/qa-run.ndjson` as its `qa_run_log`
- verify: json_path(path="$.qa_run_log", equals="qa/qa-run.ndjson")
- returns: accumulated artifact problems plus parsed context and manifest dictionaries, using empty dictionaries after parse or shape failures
- verify: json_path(path="$.parsed_artifacts", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::_artifact_problems`

### _obligation_problems
- sig: `_obligation_problems(context: dict, data: dict) -> list[str]`
- does: requires every context obligation whose `required` flag is absent or true to have a matching evidence verdict
- verify: count(subject="required OKF obligations with verdicts", equals=1)
- does: ignores context-only obligations explicitly marked `required=false`
- verify: count(subject="context-only obligations excluded", equals=1)
- does: requires each required passing obligation to include executed `log_refs`
- verify: count(subject="required obligation execution references", equals=1)
- returns: an empty list only when all required obligations have passing verdicts and executed log references
- verify: json_path(path="$.problems", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::_obligation_problems`
- tests: `workflows/tests/coder/qa/test_evidence_scope.py::test_a_required_obligation_needs_executed_logs_behind_its_pass`

### _parity_problems
- sig: `_parity_problems(cid: str, criterion: dict, root: Path, spec_dir: Path) -> list[str]`
- does: requires a non-empty per-element parity checklist
- verify: count(subject="parity checklist rows", equals=1)
- does: rejects every checklist row whose verdict is not `match`
- verify: count(subject="parity divergent rows", equals=0)
- does: requires each checklist row to cite an existing evidence file
- verify: count(subject="parity row evidence files", equals=1)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::_parity_problems`

### _data_entry_problems
- sig: `_data_entry_problems(cid: str, criterion: dict, root: Path, spec_dir: Path) -> list[str]`
- does: requires a persistence proof object for a data-entry pass
- verify: count(subject="data-entry persistence proofs", equals=1)
- does: requires persisted values to be confirmed after reload
- verify: json_path(path="$.persistence.persisted", equals=true)
- does: rejects a data-entry pass that reports bleed to other fields
- verify: json_path(path="$.persistence.bled_to_others", equals=false)
- does: requires the persistence proof to cite an existing evidence file
- verify: count(subject="data-entry persistence evidence files", equals=1)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::_data_entry_problems`

### _transient_problems
- sig: `_transient_problems(cid: str, criterion: dict, root: Path, spec_dir: Path) -> list[str]`
- does: requires transient feedback to be observed appearing after its trigger
- verify: json_path(path="$.transient.appeared", equals=true)
- does: requires transient feedback to be observed disappearing
- verify: json_path(path="$.transient.disappeared", equals=true)
- does: requires a capture file taken while the feedback was visible
- verify: count(subject="transient mid-window captures", equals=1)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::_transient_problems`

### _criteria_problems
- sig: `_criteria_problems(criteria: list, root: Path, spec_dir: Path) -> list[str]`
- does: rejects criteria with a missing or unsupported kind
- verify: count(subject="supported QA criterion kinds", equals=4)
- does: rejects criteria whose verdict is not `pass` or `fail`
- verify: count(subject="valid QA criterion verdicts", equals=2)
- does: rejects a `fail` criterion when the overall claim is a pass
- verify: count(subject="failing criteria in a claimed pass", equals=0)
- does: requires each passing criterion to cite at least one existing evidence file
- verify: count(subject="passing criteria with evidence files", equals=1)
- does: applies parity, data-entry, and transient proof requirements to their matching kinds
- verify: count(subject="specialized QA criterion proof modes", equals=3)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::_criteria_problems`

### _unsupported_pass_problems
- sig: `_unsupported_pass_problems(criteria: list, spec_dir: Path) -> list[str]`
- does: rejects a passing criterion whose referenced scenario has any FAIL assertion in the scored run log
- verify: count(subject="passing criteria backed by failed scenarios", equals=0)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::_unsupported_pass_problems`
- tests: `workflows/tests/coder/qa/test_evidence_unsupported_pass.py::test_a_pass_may_not_omit_its_scenarios_failures`

### _visual_fidelity_problems
- sig: `_visual_fidelity_problems(data: dict, root: Path, spec_dir: Path) -> tuple[list[str], list[str]]`
- does: validates each visual-fidelity report reference and requires a JSON report with a summary object
- verify: count(subject="visual fidelity JSON summaries", equals=1)
- does: treats a non-zero `missingCount` as a problem
- verify: count(subject="missing manifested visual elements", equals=0)
- does: records unexpected and unlabeled counts as informational notes when no manifested element is missing
- verify: count(subject="visual fidelity informational notes", equals=1)
- returns: separate problem and note lists for the gate to combine without treating informational buckets as failures
- verify: json_path(path="$.notes", matches=".*unexpected=[0-9]+ unlabeled=[0-9]+ .*informational only.*")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::_visual_fidelity_problems`

### _report_problems
- sig: `_report_problems(spec_dir: Path, data: dict) -> list[str]`
- does: requires `qa-report.md` to exist and carry a runner-produced run marker
- verify: count(subject="reviewer QA reports", equals=1)
- does: rejects a report whose run marker differs from the evidence `runId`
- verify: count(subject="same-run QA report markers", equals=1)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::_report_problems`
- tests: `workflows/tests/coder/qa/test_evidence_report.py::test_a_report_from_an_earlier_run_fails_the_pass`

### _run_id_problems
- sig: `_run_id_problems(data: dict, manifest: dict, criteria: list) -> list[str]`
- does: requires a non-empty evidence `runId`
- verify: json_path(path="$.runId", matches=".+")
- does: requires a manifest run id to match the evidence run id when a manifest is present
- verify: count(subject="matching evidence and manifest run ids", equals=1)
- does: requires each passing criterion to cite an artifact basename listed by the current run manifest
- verify: count(subject="current-run criterion artifacts", equals=1)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::_run_id_problems`

### verify_qa_evidence
- sig: `verify_qa_evidence(logger: logging.Logger, spec_dir: str = "", claimed_status: str = "", claimed_notes: str = "", repo_dir: str = "") -> QaResult`
- does: passes through `failed`, `blocked`, and `invalid` claims without upgrading them
- verify: json_path(path="$.status", matches="failed|blocked|invalid")
- does: maps an empty or unknown claimed status to `invalid`
- verify: json_path(path="$.status", equals="invalid")
- does: rejects a claimed pass when `spec_dir` is empty or `qa-evidence.json` is missing or invalid JSON
- verify: json_path(path="$.status", equals="invalid")
- does: accepts an unmodeled surface only when the run log has at least one passing assertion and no failing assertion
- verify: count(subject="clean unmodeled-surface run logs", equals=1)
- does: includes local artifact problems in the accumulated result
- verify: count(subject="local QA artifact checks", equals=1)
- does: includes Ostler artifact-vet problems in the accumulated result
- verify: count(subject="Ostler QA artifact checks", equals=1)
- does: includes required-obligation problems in the accumulated result
- verify: count(subject="required-obligation checks", equals=1)
- does: includes criterion-shape problems in the accumulated result
- verify: count(subject="criterion-shape checks", equals=1)
- does: includes failed-scenario problems in the accumulated result
- verify: count(subject="failed-scenario checks", equals=1)
- does: includes visual-fidelity problems in the accumulated result
- verify: count(subject="visual-fidelity checks", equals=1)
- does: includes run-identity problems in the accumulated result
- verify: count(subject="run-identity checks", equals=1)
- does: includes reviewer-report problems in the accumulated result
- verify: count(subject="reviewer-report checks", equals=1)
- does: returns `invalid` with all accumulated diagnostics when any evidence check fails
- verify: json_path(path="$.status", equals="invalid")
- returns: `QaResult(status="passed", notes=...)` only when every applicable proof check passes, retaining visual-fidelity notes and claimed notes
- verify: json_path(path="$.status", equals="passed")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/evidence.py::verify_qa_evidence`
- tests: `workflows/tests/coder/qa/test_flow.py::test_one_clean_pass_through_every_gate`
