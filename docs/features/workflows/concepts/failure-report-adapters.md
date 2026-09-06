---
type: concept
slug: failure-report-adapters
title: Failure report adapters
---
# Failure report adapters

The shared failure module converts three gate result vocabularies into the [Failure report](../failure-report.md)
format. It performs no I/O, logging, or finding parsing; callers hand it the result already held in
the current state. All three constructors preserve the caller's source context and clip captured
output before the repair turn sees it.

- code: `workflows/src/workhorse_workflows/coder/shared/failure.py`
- tests: `workflows/tests/coder/shared/test_gates.py::test_the_report_names_the_gate_that_went_red`

## Fields

### MAX_OUTPUT
- type: `int`
- default: `12000`
- required: true
- semantics: maximum number of trailing output characters retained in a failure report
- verify: count(subject="failure report output limit", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/failure.py::MAX_OUTPUT`

## Methods

### _clip
- sig: `_clip(output: str) -> str`
- does: strips leading and trailing whitespace from captured output
- does: returns stripped output unchanged when it is at most `MAX_OUTPUT` characters
- does: retains only the final `MAX_OUTPUT` characters when output is longer
- returns: bounded text, prefixed with an earlier-output-trimmed marker when clipping occurred
- verify: count(subject="bounded failure output", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/failure.py::_clip`

### from_gate
- sig: `from_gate(outcome: GateOutcome, cwd: str, lap: int) -> FailureReport`
- does: uses the gate name from `outcome.gate`, falling back to `gate` when the name is empty
- does: copies the gate command, working directory, clipped output, and repair lap into a report
- does: leaves structured findings empty rather than deriving findings from gate text
- returns: a `FailureReport` for a declared gate outcome
- verify: count(subject="gate failure report conversions", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/failure.py::from_gate`
- tests: `workflows/tests/coder/shared/test_gates.py::test_the_report_names_the_gate_that_went_red`

### from_command
- sig: `from_command(source: str, command: str, cwd: str, output: str, lap: int) -> FailureReport`
- does: accepts any gate source name without requiring it to be known by this package
- does: preserves source, command, working directory, and lap while clipping command output
- returns: a `FailureReport` for a command-only gate verdict with no structured findings
- verify: count(subject="generic command failure report conversions", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/failure.py::from_command`

### from_findings
- sig: `from_findings(source: str, findings: Sequence[Finding], cwd: str, lap: int, output: str = "") -> FailureReport`
- does: copies structured findings into a new list so the report owns its collection
- does: preserves source, working directory, and lap while clipping optional accompanying output
- returns: a `FailureReport` carrying the supplied findings instead of parsing output text
- verify: count(subject="structured failure report conversions", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/failure.py::from_findings`
