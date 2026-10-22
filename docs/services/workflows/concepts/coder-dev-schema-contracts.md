---
type: concept
slug: coder-dev-schema-contracts
title: Coder development schema contracts
---
# Coder development schema contracts

The `coder.shared.schemas.dev` module defines the typed values crossing the development flow's
plan, implementation, gate, repair, and operator-result boundaries. Agent-facing statuses are
closed literals; Python-produced results use defaults where the producing node owns the value.
Nested plan and dispatch records preserve service paths, verification setup, fixtures, and source
provenance without requiring later nodes to re-parse agent-authored files.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::__all__` @bcd75ac6f796
- detail: [coder shared development helpers](coder-shared-dev.md)
- detail: [coder rendered schema contracts](coder-render-schema-contracts.md)
- detail: [failure report](../formats/failure-report.md)
- detail: [operator gate result](../formats/operator-gate.md)
- detail: [coder operator resolution result](../formats/coder-operator-resolution.md)
- detail: [coder implementation result](../formats/impl-result.md)
- detail: [coder operator answer](../formats/operator-answer.md)
- detail: [coder plan validation](../formats/plan-validation.md)
- detail: [coder dispatch entry](../formats/dispatch-entry.md)
- detail: [coder story source](../formats/story-source.md)
- detail: [coder story sources](../formats/story-sources.md)
- detail: [coder QA run entry](../formats/qa-run-entry.md)
- detail: [coder plan summary](../formats/plan-summary.md)
- detail: [coder implementation context](../formats/impl-context.md)
- detail: [coder branch outcome](../formats/branch-outcome.md)
- detail: [coder gate outcome](../formats/gate-outcome.md)
- detail: [coder story status check](../formats/story-status-check.md)
- detail: [coder gate list](../formats/gate-list.md)
- detail: [coder changed files](../formats/changed-files.md)
- detail: [coder development outcome](../formats/dev-result.md)
- detail: [coder development story result](../formats/dev-story-result.md)
- detail: [coder finding settlement](../formats/settlement.md)

`lift_fixture` converts a bare fixture key to a named declaration and treats non-key prose as a
`provides` description. `PlanFields` also lifts fixtures nested under `verification_setup` and
`shared_packages` accepts bare paths. `FailureReport`, `OperatorGate`, and `OperatorResolution`
are documented in their existing format nodes rather than duplicated here.

## Methods

### lift_fixture
- sig: `lift_fixture(item: str) -> dict[str, str]`
- does: treats an identifier-shaped string as a fixture name
- does: treats any other string as a fixture provision description
- returns: a mapping with `name` or with empty `name` and `provides`
- verify: json_path(path="$.name", equals="acme")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::lift_fixture` @bcd75ac6f796
