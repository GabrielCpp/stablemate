---
type: flow
slug: coder-docs
title: Coder documentation flow
---
# Coder documentation flow

The `Docs` machine folds one completed story into the current OKF book. It resolves the story
and documentation context, distinguishes an unmanaged book from an unusable one, and builds the
grounding worklist from the code diff. One owner turn then writes the book, has its subagents
review it and fixes what they find. The flow gates the result against direct grounding and sends
a failed gate back to the owner as a report. It is entered by the Coder main flow or directly
with `workhorse-coder run docs`.
- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-coder.dot")
- steps:
  - [run](../workhorse-coder.md#run)
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [coder handoff boundary contract](../concepts/coder-handoff-boundary.md)
- detail: [coder docs package](../concepts/coder-docs-package.md)
- detail: [coder main flow](coder-main.md)
- detail: [coder docs subflow package](../concepts/coder-docs-subflow.md)
- detail: [coder shared documentation helpers](../concepts/coder-shared-documentation.md)
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_inside_the_docs_worktree_take_the_local_route`
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_outside_the_docs_worktree_take_the_semantic_route`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_failed_check_goes_back_to_the_owner_as_one_report`
- tests: `workflows/tests/coder/docs/test_flow.py::test_checks_that_stay_red_past_the_lap_budget_park_instead_of_failing`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_repair_lap_with_nothing_left_to_edit_keeps_the_nodes_already_named`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_block_is_put_to_the_author_before_anyone_is_asked`
- tests: `workflows/tests/coder/docs/test_flow.py::test_an_epic_scoped_answer_blocks_the_story_with_the_answer_as_the_finding`

The Python entry is `Docs` in `workflows/src/workhorse_workflows/coder/docs/flow.py`. The class
declares the labelled checkpoints and the owner, check, resolve and read-operator turns the flow
orchestrates.

`story`, `epic`, `target_env`, `preexisting`, and `operator_mode`
are checkpointed inputs. The `workspace` name is ambient and follows the run; `target_env` defaults to `local`, and `operator_mode` defaults to `auto`.

The stages, in order: [setup](#setup), [context-classification](#context-classification), [own-the-book](#own-the-book), [grounding-gate](#grounding-gate), [operator-block](#operator-block).

The flow starts when the configured story slug resolves to a readable story before any documentation turn; or when the repository has a usable OKF book and a classified documentation context.
It ends in one of these ways: a passing grounding gate returns a passed result containing every node authored during the flow; an absent OKF book returns not-applicable without an agent turn; an unusable OKF book fails before documentation; an epic-scoped operator answer returns a blocked result carrying the answer.

## Steps

### setup

- kind: prepare

The flow resolves workspace directories and prepares the requested story. An empty or
unresolvable story path raises a workflow failure before OKF detection or an agent turn. Every
entry resets the story's documentation conversation so a resume or post-fix pass cannot reuse a
conversation describing an older book. Every terminal return resets it too.

`Docs.labels` exposes the resolved story slug as the `work_id` activity label when one exists.
`Docs.state_labels` adds the lap, block and number counters carried in the state.

### context-classification

- kind: prepare

The flow first detects the OKF book. No configured OKF graph is a successful `not_applicable`
result and spends no agent turn; an unusable graph is a workflow failure. It then classifies the
documentation context. A readable local source root uses the local route, where an OKF context
packet maps changed production units to graph references and is validated before the gate.
Sources outside the documentation worktree use the semantic route, where no diff packet is built.
An unreadable context is a workflow failure, not a semantic pass.

When a workspace manifest and story id are supplied, the flow also resolves story-source
provenance and fails if that mapping is invalid. It builds the initial documentation obligations
before the owner turn. Local mode records the current OKF packet status and lists ungrounded
changed production references. Semantic mode records that no worktree grounding list is
available.

### own-the-book

- kind: drive
- detail: [coder document-story prompt](../formats/coder-document-story-prompt.md)

One high-power `document-story` turn runs in the story's documentation conversation with no
timeout. It receives the story, epic, services root, implementation plan summary, context mode,
the grounding worklist, the last gate report and the last operator answer. The turn writes the
book and has its subagents review and repair it. It returns `documented`, `not_required`, or a
blocked result. `not_required` still proceeds to the grounding gate. It means the story changes
nothing represented by the book, not that the gate is skipped. A blocked result goes to the
operator-block step.

The returned node identities are appended to the accumulated identities with duplicates removed.
A repair lap can therefore return an empty node list without discarding nodes authored earlier.

### grounding-gate

- kind: verify

For local context the flow rebuilds the OKF packet against the post-author worktree, validates
the packet, and asks `verify_story_documentation` to check every changed production unit directly
against the accumulated authored nodes. Semantic context passes empty strings for both statuses.
Only an explicit passed gate finishes the flow. A failed gate sends its notes back to the owner
turn as the report, with the remaining `G:` references as the new worklist. After `MAX_LAPS` repair
laps the flow raises a block instead of approving or failing the whole caller run.

### operator-block

- kind: drive

In `auto` mode the shared resolver may answer a block only from an existing decision, repository
rule, installed skill, or acceptance criterion. An answered block, and a human answer, are read
from the story context and re-enter the owner turn as its operator context. In `human` or
`operator` mode, or once `MAX_BLOCKS` blocks have been spent, the flow awaits the operator on the
story context without dispatching the resolver. An epic-scoped answer cannot be applied to one
story. It ends the flow with a blocked result carrying the answer as its notes.

## Private helpers

The module's private helpers keep state transitions deterministic without becoming workflow
states. `_brief` renders the story, epic, context, services root and plan summary shared by every
owner turn. `_context_mode` treats a manifest-resolved external source repository as locally
verifiable when the resolved story sources are present, and otherwise preserves the classifier's
local or semantic mode. `_epic_path` derives the parent epic path through configured docs-root
resolution. The module exports only `Docs`.
