---
type: concept
slug: coder-fix-package
title: Coder fix package
---
# Coder fix package

The `fix` machine drains items filed in the coder backlog that were discovered during
implementation, documentation, or QA. Each selected backlog item receives one owner turn that
fixes and QAs it, then is gated and committed independently. It is a sub-flow entered by the
Coder main flow after a story passes all gates, and handles asynchronous repairs discovered
during the story's main pipeline.

The backlog is filed by any story stage when a secondary defect is encountered — a code cleanup,
a missing edge case, a documentation fix — and marked with a blocking status that prevents the
story from advancing until drained. The fix machine runs the owner prompt, the gates, and
the documentation handoff for each drained item. Items that pass all gates are committed; failed repairs
escalate to an operator gate.

- code: `workflows/src/workhorse_workflows/coder/fix/flow.py` @3221c750e52d
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix` @3221c750e52d
- detail: [coder backlog contract](coder-backlog-contract.md)

## Methods

### render_gate

- sig: `render_gate(report: FailureReport) -> str`
- does: format a FailureReport as markdown with source gate name, working directory, command, and output
- verify: json_path(path="$.rendered", matches="(?s)^The `[^`]+` gate failed in `[^`]+`\\.\\n\\nCommand: `[^`]+`\\n\\n```\\n.*\\n```$")
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::render_gate` @3221c750e52d
- tests: `workflows/tests/coder/fix/test_flow.py`

