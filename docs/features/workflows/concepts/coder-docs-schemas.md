---
type: concept
slug: coder-docs-schemas
title: Coder documentation schemas
---
# Coder documentation schemas

- The documentation lane's typed values cross deterministic nodes, agent turns, and checkpointed
  state. Agent replies use closed status vocabularies where an omitted decision must be invalid;
  Python-produced results use pessimistic defaults so an absent result cannot imply success.
- One owner turn replies with a `DocumentationResult`. The deterministic gate answers with a
  `DocumentationGate`, and the flow ends with a `DocsResult`.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::__all__` @61c0c6e9cae9
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocsStatus` @61c0c6e9cae9
- detail: [Coder story pipeline](story-pipeline.md)
- detail: [Coder documentation flow](../flows/coder-docs.md)

## Models

### method: OkfDetection
- sig: `OkfDetection(has_okf: Literal["yes", "no", "invalid"] = "no", features_root: str = "", reason: str = "") -> OkfDetection`
- does: reports whether the repository has a usable OKF graph
- verify: json_path(path="$.has_okf", matches="^(yes|no|invalid)$")
- does: carries the detected features root
- verify: json_path(path="$.features_root", equals="docs/stories")
- does: carries the detection reason
- verify: json_path(path="$.reason", equals="The slice works without it.")
- returns: a CoderResult whose default `has_okf` is `no`, so no decision cannot enter documentation
- verify: json_path(path="$.has_okf", equals="no")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::OkfDetection` @61c0c6e9cae9

### method: ContextClassification
- sig: `ContextClassification(mode: Literal["local", "semantic", "error"] = "semantic", source_roots: list[str] = [], notes: str = "") -> ContextClassification`
- does: classifies documentation grounding as local, semantic, or an unreadable error
- verify: json_path(path="$.mode", matches="^(local|semantic|error)$")
- returns: the source roots used for classification
- verify: json_path(path="$.source_roots", equals="example source roots")
- returns: classification notes alongside the mode
- verify: json_path(path="$.notes", equals="Mapped the diff to two source roots.")
- returns: the semantic mode by default, so an absent classification asks for review
- verify: json_path(path="$.mode", equals="semantic")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::ContextClassification` @61c0c6e9cae9

### method: DocumentationResult
- sig: `DocumentationResult(status: Literal["documented", "not_required", "blocked"], nodes: list[str] = [], notes: str = "") -> DocumentationResult`
- does: carries an agent's documentation decision, touched node identities, and explanation
- does: reserves `not_required` for a story whose changed production files were already directly grounded and changed no observable contract
- verify: json_path(path="$.nodes", equals="[]")
- returns: only one of documented, not_required, or blocked
- verify: json_path(path="$.status", matches="^(documented|not_required|blocked)$")
- returns: status is required and has no default
- verify: json_path(path="exception.type", equals="ValidationError")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocumentationResult` @61c0c6e9cae9

### method: DocumentationGate
- sig: `DocumentationGate(status: Literal["passed", "invalid"] = "invalid", notes: str = "", changed_code_count: int = 0, doctor_error_count: int = 0, failures: list[str] = []) -> DocumentationGate`
- does: reports direct grounding-gate status
- verify: json_path(path="$.status", matches="^(passed|invalid)$")
- does: carries changed-code and doctor-error diagnostics
- verify: json_path(path="$.changed_code_count", matches="^[0-9]+$")
- does: carries stable failure identities
- verify: json_path(path="$.failures", equals="example failures")
- returns: an invalid gate by default so an absent gate cannot approve documentation
- verify: json_path(path="$.status", equals="invalid")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocumentationGate` @61c0c6e9cae9

### method: DocumentationObligations
- sig: `DocumentationObligations(refs: list[str] = [], notes: str = "") -> DocumentationObligations`
- does: carries changed production references not yet owned by an OKF code bullet
- returns: the grounding worklist and an explanation when it could not be computed
- verify: json_path(path="$.refs", equals="example refs")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocumentationObligations` @61c0c6e9cae9

### method: DocsResult
- sig: `DocsResult(status: DocsStatus = "failed", notes: str = "", authored_nodes: list[str] = []) -> DocsResult`
- does: reports the documentation subflow's passed, not_applicable, blocked, or pessimistic failed outcome
- returns: the terminal status, notes, and accumulated authored node identities
- verify: json_path(path="$.status", equals="failed")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/docs.py::DocsResult` @61c0c6e9cae9
