---
type: concept
slug: coder-dev-package
title: Coder dev package
---
# Coder dev package

The `dev` machine builds one story with one owner turn and checks the result. It is a sub-flow
entered by the Coder main flow when a story is ready for implementation, and can also be run
directly with `workhorse-coder run dev`.

The owner turn plans, builds, reviews and fixes through its own subagents, and answers every
finding in the story's answer file. The flow around it is deterministic. It records the plan,
runs the declared service gates, settles the findings against the answers, and checks that the
story left nothing uncommitted. A failed check goes back to the owner as a report for another
repair lap. A spent lap budget escalates to an operator gate.

- code: `workflows/src/workhorse_workflows/coder/dev/flow.py` @43ea3e1c6c82
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev` @43ea3e1c6c82
- tests: `workflows/tests/coder/dev/test_flow.py`
- detail: [coder dev flow](../flows/coder-dev.md)

The dev package operates against a docs repository carrying one epic with its `## Stories`
listing and one authored story, and against a workspace file naming the code repositories the
plan dispatches into. The `docs` and `workspace` test fixtures stand those inputs up. `docs`
builds the docs repo. `workspace` builds two real git repositories and a home config whose
`acme` workspace names them, as an operator ships one. The gates the
flow runs therefore see the same artifacts the production flow does.

## Methods

### plan_arg
- sig: `plan_arg(result: DevResult) -> dict[str, Any]`
- does: keeps only the structural half of the owner's reply that `record_plan` takes
- verify: count(subject="plan structure fields", equals=5)
- returns: the services, implementation order, shared packages, verification setup and fixtures
- verify: json_path(path="$.services", equals="example services")
- code: `workflows/src/workhorse_workflows/coder/dev/report.py::plan_arg` @7612f350c91a

### report_text
- sig: `report_text(report: FailureReport) -> str`
- does: renders a gate failure as the markdown the next owner turn reads
- verify: count(subject="rendered gate reports", equals=1)
- does: names the gate, then the command and directory when they are known, then each finding with its repair
- verify: count(subject="rendered report findings", equals=1)
- does: appends the gate output in a fence when it is not blank
- verify: count(subject="fenced report outputs", equals=1)
- returns: a markdown string starting with `Gate: <source>`
- verify: json_path(path="$.report", matches="^Gate: ")
- code: `workflows/src/workhorse_workflows/coder/dev/report.py::report_text` @7612f350c91a

### findings_text
- sig: `findings_text(items: Sequence[wl.WorkItem]) -> str`
- does: renders one `###` section per open finding item, with its source, target, issue and repair
- verify: count(subject="rendered finding sections", equals=1)
- does: shows `(no target)` for a finding with no target
- verify: count(subject="targetless finding sections", equals=1)
- returns: the sections joined by blank lines
- verify: json_path(path="$.findings", equals="example findings")
- code: `workflows/src/workhorse_workflows/coder/dev/report.py::findings_text` @7612f350c91a

### rejected_text
- sig: `rejected_text(rejected: dict[str, str], errors: Sequence[str]) -> str`
- does: lists each rejected answer id with the reason its evidence did not hold
- verify: count(subject="rejected answer lines", equals=1)
- does: appends each settlement error as its own bullet
- verify: count(subject="settlement error lines", equals=1)
- returns: one bullet per line
- verify: json_path(path="$.rejected", equals="example rejected")
- code: `workflows/src/workhorse_workflows/coder/dev/report.py::rejected_text` @7612f350c91a
