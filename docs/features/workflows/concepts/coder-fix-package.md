---
type: concept
slug: coder-fix-package
title: Coder fix package
---
# Coder fix package

The `fix` machine drains items filed in the coder backlog that were discovered during
implementation, documentation, or QA. Each selected backlog item receives an agent turn to
implement the fix, then is gated and committed independently. It is a sub-flow entered by the
Coder main flow after a story passes all gates, and handles asynchronous repairs discovered
during the story's main pipeline.

The backlog is filed by any story stage when a secondary defect is encountered — a code cleanup,
a missing edge case, a documentation fix — and marked with a blocking status that prevents the
story from advancing until drained. The fix machine chains implementation, documentation, and
gatekeeping prompts for each drained item. Items that pass all gates are committed; failed repairs
escalate to an operator gate.

- code: `workflows/src/workhorse_workflows/coder/fix/flow.py`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix`
- tests: `workflows/tests/coder/test_fix.py`
- detail: [coder backlog contract](coder-backlog-contract.md)

## Methods

### render_gate

- sig: `render_gate(report: FailureReport) -> str`
- does: format a FailureReport as markdown with lap number, source gate name, command, working directory, and output
- verify: json_path(path="$.rendered", matches="(?s)^Repair lap \\d+: the `[^`]+` gate failed in `[^`]+`\\.\\n\\nCommand: `[^`]+`\\n\\n```\\n.*\\n```$")
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::render_gate`
- tests: `workflows/tests/coder/fix/test_flow.py`

