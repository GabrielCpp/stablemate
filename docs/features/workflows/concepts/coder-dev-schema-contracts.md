---
type: concept
slug: coder-dev-schema-contracts
title: Coder development schema contracts
---
# Coder development schema contracts

The `coder.shared.schemas.dev` module defines the typed values crossing the development flow's
plan, implementation, gate, repair, lap, and operator-result boundaries. Agent-facing statuses are
closed literals; Python-produced results use defaults where the producing node owns the value.
Nested plan and dispatch records preserve service paths, verification setup, fixtures, and source
provenance without requiring later nodes to re-parse agent-authored files.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::__all__`
- detail: [coder shared development helpers](coder-shared-dev.md)
- detail: [coder rendered schema contracts](coder-render-schema-contracts.md)
- detail: [failure report](../failure-report.md)
- detail: [operator gate result](../operator-gate.md)
- detail: [coder operator resolution result](../coder-operator-resolution.md)
- detail: [coder plan result](../coder-plan-result.md)
- detail: [coder implementation result](../impl-result.md)
- detail: [coder operator answer](../operator-answer.md)
- detail: [coder plan validation](../plan-validation.md)
- detail: [coder dispatch entry](../dispatch-entry.md)
- detail: [coder story source](../story-source.md)
- detail: [coder story sources](../story-sources.md)
- detail: [coder QA run entry](../qa-run-entry.md)
- detail: [coder plan summary](../plan-summary.md)
- detail: [coder implementation context](../impl-context.md)
- detail: [coder branch outcome](../branch-outcome.md)
- detail: [coder layer pick](../layer-pick.md)
- detail: [coder gate outcome](../gate-outcome.md)
- detail: [coder story status check](../story-status-check.md)
- detail: [coder gate list](../gate-list.md)
- detail: [coder repair lap](../lap.md)
- detail: [coder changed files](../changed-files.md)
- detail: [coder development result](../dev-result.md)

`lift_fixture` converts a bare fixture key to a named declaration and treats non-key prose as a
`provides` description. `PlanResult` also lifts fixtures nested under `verification_setup` and
`shared_packages` accepts bare paths. `FailureReport`, `OperatorGate`, and `OperatorResolution`
are documented in their existing format nodes rather than duplicated here.

## Methods

### lift_fixture
- sig: `lift_fixture(item: str) -> dict[str, str]`
- does: treats an identifier-shaped string as a fixture name
- does: treats any other string as a fixture provision description
- returns: a mapping with `name` or with empty `name` and `provides`
- verify: json_path(path="$.name", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::lift_fixture`
