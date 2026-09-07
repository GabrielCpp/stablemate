---
type: concept
slug: coder-docs-schemas
title: Coder documentation schemas
---
# Coder documentation schemas

- The documentation lane's typed values cross deterministic nodes, agent turns, and checkpointed
  state. Agent replies use closed status vocabularies where an omitted decision must be invalid;
  Python-produced results use pessimistic defaults so an absent result cannot imply success.
- `DocsProgress` records the last decision and outstanding identities for each independent gate
  lane. `DocsLoop` carries the repair counters, notes, obligations, authored node identities, and
  progress bundle across resumes.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::__all__`
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocsStatus`
- detail: [Coder story pipeline](story-pipeline.md)
- detail: [Coder documentation flow](../flows/coder-docs.md)
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_failed_gate_reworks_before_the_reviewer_ever_runs`
- tests: `workflows/tests/coder/test_telemetry.py::test_docs_reports_its_gates_and_whether_the_rework_bought_anything`

## Models

### method: OkfDetection
- sig: `OkfDetection(has_okf: Literal["yes", "no", "invalid"] = "no", features_root: str = "", reason: str = "") -> OkfDetection`
- does: reports whether the repository has a usable OKF graph
- verify: json_path(path="$.has_okf", matches="^(yes|no|invalid)$")
- does: carries the detected features root
- verify: json_path(path="$.features_root", matches=".*")
- does: carries the detection reason
- verify: json_path(path="$.reason", matches=".*")
- returns: a CoderResult whose default `has_okf` is `no`, so no decision cannot enter documentation
- verify: json_path(path="$.has_okf", equals="no")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::OkfDetection`

### method: ContextClassification
- sig: `ContextClassification(mode: Literal["local", "semantic", "error"] = "semantic", source_roots: list[str] = [], notes: str = "") -> ContextClassification`
- does: classifies documentation grounding as local, semantic, or an unreadable error
- returns: the source roots used for classification
- verify: json_path(path="$.source_roots", matches=".*")
- returns: classification notes alongside the mode
- verify: json_path(path="$.notes", matches=".*")
- verify: json_path(path="$.mode", equals="semantic")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::ContextClassification`

### method: WorktreeSnapshot
- sig: `WorktreeSnapshot(entries: list[str] = [], notes: str = "") -> WorktreeSnapshot`
- does: carries pre-existing dirty worktree entries as path-and-content hashes
- returns: the entries and snapshot notes used to distinguish operator edits from story changes
- verify: json_path(path="$.entries", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::WorktreeSnapshot`

### method: DocumentationResult
- sig: `DocumentationResult(status: Literal["documented", "not_required", "blocked"], nodes: list[str] = [], notes: str = "") -> DocumentationResult`
- does: carries an agent's documentation decision, touched node identities, and explanation
- returns: only one of documented, not_required, or blocked
- verify: json_path(path="$.status", matches="^(documented|not_required|blocked)$")
- returns: status is required and has no default
- verify: json_path(path="exception.type", equals="ValidationError")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocumentationResult`

### method: DocumentationGate
- sig: `DocumentationGate(status: Literal["passed", "invalid"] = "invalid", notes: str = "", changed_code_count: int = 0, doctor_error_count: int = 0, failures: list[str] = []) -> DocumentationGate`
- does: reports direct grounding-gate status
- verify: json_path(path="$.status", matches="^(passed|invalid)$")
- does: carries changed-code and doctor-error diagnostics
- verify: json_path(path="$.changed_code_count", matches="^[0-9]+$")
- does: carries stable failure identities
- verify: json_path(path="$.failures", matches=".*")
- returns: an invalid gate by default so an absent gate cannot approve documentation
- verify: json_path(path="$.status", equals="invalid")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocumentationGate`

### method: DocumentationObligations
- sig: `DocumentationObligations(refs: list[str] = [], notes: str = "") -> DocumentationObligations`
- does: carries changed production references not yet owned by an OKF code bullet
- returns: the grounding worklist and an explanation when it could not be computed
- verify: json_path(path="$.refs", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocumentationObligations`

### method: DocumentationFinding
- sig: `DocumentationFinding(id: str = "", kind: Literal["node-type", "missing-node", "flow-coverage", "overclaim", "bullet-granularity", "grounding", "verify-overclaim", "author-decision"], target: str = "", issue: str = "", repair: str = "") -> DocumentationFinding`
- does: identifies one semantic documentation defect and its actionable target and repair
- returns: a finding with a closed defect kind and stable id
- verify: json_path(path="$.kind", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocumentationFinding`

### method: DocumentationReview
- sig: `DocumentationReview(status: Literal["approved", "revise", "blocked"], findings: list[DocumentationFinding] = [], notes: str = "") -> DocumentationReview`
- does: carries the independent review disposition and structured findings
- returns: an approved, revise, or blocked review
- verify: json_path(path="$.status", matches="^(approved|revise|blocked)$")
- returns: status has no default
- verify: json_path(path="exception.type", equals="ValidationError")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocumentationReview`

### method: DocsProgress
- sig: `DocsProgress(gate_verdict: Literal["", "passed", "invalid"] = "", review_disposition: Literal["", "approved", "revise", "blocked"] = "", gate_progress_verdict: ProgressVerdict | Literal[""] = "", review_progress_verdict: ProgressVerdict | Literal[""] = "", gate_failures: int = 0, review_findings: int = 0, gate_ids: list[str] = [], review_ids: list[str] = [], chain_laps: int = 0) -> DocsProgress`
- does: records the latest gate and review decisions
- verify: json_path(path="$.gate_verdict", matches=".*")
- does: records failure and finding counts
- verify: json_path(path="$.gate_failures", matches="^[0-9]+$")
- does: records failing identities and repair-chain laps
- verify: json_path(path="$.gate_ids", matches=".*")
- returns: a checkpointable progress value with empty verdicts and zero counts before either lane runs
- verify: json_path(path="$.chain_laps", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocsProgress`

### method: DocsLoop
- sig: `DocsLoop(rework: int = 0, review_rework: int = 0, blocks: int = 0, gate_notes: str = "", review_notes: str = "", obligations: tuple[str, ...] = (), authored_nodes: tuple[str, ...] = (), progress: DocsProgress = DocsProgress(), overruns: int = 0) -> DocsLoop`
- does: carries documentation repair inputs across resumed passes
- verify: json_path(path="$.obligations", matches=".*")
- does: carries repair counters across resumed passes
- verify: json_path(path="$.rework", matches="^[0-9]+$")
- returns: a state bundle with zero counters, empty worklists, and fresh progress by default
- verify: json_path(path="$.rework", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocsLoop`

### method: RepairOverran
- sig: `RepairOverran(status: Literal["overran"] = "overran", lap: int = 0, notes: str = "") -> RepairOverran`
- does: records that a repair turn exceeded its wall-clock budget without fabricating an author result
- returns: an overran marker with the lap number and notice
- verify: json_path(path="$.status", equals="overran")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::RepairOverran`

### method: DocsResult
- sig: `DocsResult(status: DocsStatus = "failed", notes: str = "", authored_nodes: list[str] = []) -> DocsResult`
- does: reports the documentation subflow's passed, not_applicable, blocked, or pessimistic failed outcome
- returns: the terminal status, notes, and accumulated authored node identities
- verify: json_path(path="$.status", equals="failed")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocsResult`

## Methods

### after_gate
- sig: `DocsProgress.after_gate(gate: DocumentationGate) -> DocsProgress`
- does: records the gate status and failure count
- verify: json_path(path="$.gate_verdict", matches=".*")
- does: computes progress against the prior failure identities
- verify: json_path(path="$.gate_progress_verdict", matches=".*")
- does: replaces the gate identity baseline
- verify: json_path(path="$.gate_ids", matches=".*")
- returns: a copied progress value containing the current gate decision
- verify: json_path(path="$.gate_failures", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocsProgress.after_gate`

### after_review
- sig: `DocsProgress.after_review(review: DocumentationReview) -> DocsProgress`
- does: records the review disposition and finding count, retaining finding identities only for revise
- returns: a copied progress value containing the current review decision
- verify: json_path(path="$.review_findings", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocsProgress.after_review`
