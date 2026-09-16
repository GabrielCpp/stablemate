---
type: format
slug: failure-report
title: Failure report
---
# Failure report

The in-memory hand-off from a deterministic gate to the repair role. It preserves the gate's
identity, exact command, working directory, bounded captured output, optional structured findings,
and one-based repair lap. Gate adapters create it in Python; an agent never paraphrases the gate
evidence.

- file: none — in-memory workflow result
- config: `FailureReport` fields are produced by the coder gate adapters
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::FailureReport` @b6e19c205b4f
- detail: [failure report adapters](../concepts/failure-report-adapters.md)

## Fields

### source
- type: `str`
- default: empty string
- required: false
- semantics: name of the gate or structured verdict source that failed
- verify: json_path(path="$.source", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::FailureReport.source` @b6e19c205b4f

### command
- type: `str`
- default: empty string
- required: false
- semantics: command captured verbatim so the repair turn can rerun the same gate
- verify: json_path(path="$.command", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::FailureReport.command` @b6e19c205b4f

### cwd
- type: `str`
- default: empty string
- required: false
- semantics: working directory in which the failing gate ran
- verify: json_path(path="$.cwd", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::FailureReport.cwd` @b6e19c205b4f

### output
- type: `str`
- default: empty string
- required: false
- semantics: captured gate output, stripped and limited to the final 12000 characters when longer
- verify: json_path(path="$.output", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::FailureReport.output` @b6e19c205b4f

### findings
- type: `list[Finding]`
- default: empty list
- required: false
- semantics: structured findings supplied by review or QA instead of parsed command output
- verify: json_path(path="$.findings", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::FailureReport.findings` @b6e19c205b4f

### lap
- type: `int`
- default: `0`
- required: false
- semantics: one-based repair lap carried into the repair prompt and run log
- verify: json_path(path="$.lap", matches="[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::FailureReport.lap` @b6e19c205b4f
