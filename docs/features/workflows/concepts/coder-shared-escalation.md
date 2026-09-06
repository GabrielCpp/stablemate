---
type: concept
slug: coder-shared-escalation
title: Coder escalation composition
---
# Coder escalation composition

The coder shared escalation module produces the complete markdown body that a workflow parks in
an operator gate. It reads the existing story context before composing a new body, so a resolver's
investigation and earlier operator answers survive the overwrite performed by `Await`. Per-story
flows derive story identity from their workflow context; the backlog-drain lane supplies the story
explicitly because its workflow context identifies the workspace instead.

- code: `workflows/src/workhorse_workflows/coder/shared/escalation.py`
- detail: [operator gate result](../operator-gate.md)
- detail: [coder operator resolution result](../coder-operator-resolution.md)
- detail: [Coder story paths](../story-paths.md)
- detail: [Coder finding](../finding.md)

The body starts with `STATUS: AWAITING_OPERATOR`, identifies the escalation and story, then places
the block, resolver investigation, node findings, unblock summary, locations, and bounded earlier
history in reader order. Empty optional sections are omitted except for the explanation that no
automatic resolver ran.

## Fields

### HISTORY_HEAD
- type: `int`
- default: `4000`
- required: true
- semantics: characters retained from the beginning of an oversized prior context
- verify: json_path(path="$.result", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/escalation.py::HISTORY_HEAD`

### HISTORY_TAIL
- type: `int`
- default: `8000`
- required: true
- semantics: characters retained from the end of an oversized prior context
- verify: json_path(path="$.result", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/escalation.py::HISTORY_TAIL`

## Methods

### compose_escalation
- sig: `compose_escalation(logger: logging.Logger, story_path: str = "", story_slug: str = "", spec_dir: str = "", run_dir: str = "", number: int = 0, block_kind: str = "", block_notes: str = "", where: str = "", tried: list[str] | None = None, summary: str = "", findings: list[Finding] | None = None) -> OperatorGate`
- does: reads the existing `context.md` beside `story_path` when that file exists
- verify: json_path(path="$.body", matches=".*What blocked.*")
- does: publishes the first status line as `STATUS: AWAITING_OPERATOR`
- verify: json_path(path="$.result", matches="^STATUS: AWAITING_OPERATOR")
- does: includes the escalation ordinal and story identity
- verify: json_path(path="$.body", matches=".*Escalation #[0-9]+ for story.*")
- does: includes the block details and resolver attempts in reader order
- verify: json_path(path="$.body", matches=".*What blocked.*What the resolver tried.*")
- does: includes supplied findings and the resolver's unblock summary
- verify: json_path(path="$.body", matches=".*What the node found.*What would unblock it.*")
- does: includes each non-empty location in the locations section
- verify: json_path(path="$.body", matches=".*Where everything is.*")
- does: explains that no automatic resolver ran when `tried` is empty
- verify: json_path(path="$.body", matches=".*no auto-resolver ran.*")
- does: retains the first 4000 and last 8000 characters of oversized prior context and states the number of elided characters
- verify: json_path(path="$.body", matches=".*characters elided.*")
- returns: an `OperatorGate` containing the complete context body and one-based escalation number
- verify: json_path(path="$.number", matches="[1-9][0-9]*")
- code: `workflows/src/workhorse_workflows/coder/shared/escalation.py::compose_escalation`
- tests: `workflows/tests/coder/shared/test_escalation.py::test_the_gate_is_a_whole_context_file_the_engine_leaves_alone`
- tests: `workflows/tests/coder/shared/test_escalation.py::test_the_resolver_s_note_survives_the_write_that_would_have_erased_it`
- tests: `workflows/tests/coder/shared/test_escalation.py::test_the_node_s_own_findings_reach_the_operator`

### escalation
- sig: `escalation(flow: Workflow, *, block_kind: str, where: str, notes: str, number: int = 1, result: OperatorResolution | None = None, findings: Sequence[Finding] = (), story: StoryPaths | None = None) -> OperatorGate`
- does: selects the explicit `story` identity when supplied and otherwise uses `flow.ctx`
- verify: json_path(path="$.result", matches=".*story.*")
- does: converts resolver `tried` and `summary`, or empty values without a resolver, into arguments for `compose_escalation`
- verify: json_path(path="$.result", matches=".*What the resolver tried.*")
- returns: the `OperatorGate` produced for the block without imposing an escalation-count cap
- verify: json_path(path="$.result", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/escalation.py::escalation`

### context_path
- sig: `context_path(flow: Workflow, story_path: str = "") -> Path`
- does: resolves `context.md` beside the explicit story path when one is supplied
- verify: json_path(path="$.result", matches=".*context\\.md")
- does: otherwise resolves `context.md` beside `flow.ctx.story_path`
- verify: json_path(path="$.result", matches=".*context\\.md")
- returns: the path an `Await` writes operator questions into
- verify: json_path(path="$.result", matches=".*context\\.md")
- code: `workflows/src/workhorse_workflows/coder/shared/escalation.py::context_path`
