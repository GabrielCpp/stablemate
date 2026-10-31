---
type: flow
slug: coder-docs
title: Coder documentation flow
---
# Coder documentation flow

The `Docs` machine writes one story into the current OKF book, in one of two phases. The `spec`
phase runs before dev: it writes the story's behaviour model and the book delta it implies, with
no code to read. The `build` phase, the default, runs after dev: it folds the finished story into
the book. The `build` phase resolves the story and documentation context, distinguishes an
unmanaged book from an unusable one, and builds the grounding worklist from the code diff. In
either phase one owner turn writes the book, has its subagents review it and fixes what they
find. The flow gates the result and sends a failed gate back to the owner as a report. It is
entered by the Coder main flow or directly with `workhorse-coder run docs`.
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
- detail: [coder lane order](../concepts/coder-lane-order.md)
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_inside_the_docs_worktree_take_the_local_route`
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_outside_the_docs_worktree_take_the_semantic_route`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_failed_check_goes_back_to_the_owner_as_one_report`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_book_that_does_not_compile_goes_back_to_the_owner_with_its_gaps`
- tests: `workflows/tests/coder/docs/test_flow.py::test_the_spec_pass_never_compiles_the_book`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_failing_exercise_goes_back_to_the_owner_once_as_a_repair_report`
- tests: `workflows/tests/coder/docs/test_flow.py::test_an_exercise_that_still_fails_after_one_bounce_passes_to_qa`
- tests: `workflows/tests/coder/docs/test_flow.py::test_an_exercise_that_cannot_run_fails_the_gate_and_goes_back_as_a_lap`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_plan_that_already_stands_skips_the_exercise`
- tests: `workflows/tests/coder/docs/test_flow.py::test_checks_that_stay_red_past_the_lap_budget_park_instead_of_failing`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_repair_lap_with_nothing_left_to_edit_keeps_the_nodes_already_named`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_block_is_put_to_the_author_before_anyone_is_asked`
- tests: `workflows/tests/coder/docs/test_flow.py::test_an_epic_scoped_answer_blocks_the_story_with_the_answer_as_the_finding`
- tests: `workflows/tests/coder/docs/test_flow.py::test_the_spec_pass_writes_the_book_before_any_diff_exists`
- tests: `workflows/tests/coder/test_session_chains.py::test_the_spec_pass_has_its_own_owner_conversation`

The Python entry is `Docs` in `workflows/src/workhorse_workflows/coder/docs/flow.py`. The class
declares the labelled checkpoints and the owner, check, resolve and read-operator turns the flow
orchestrates.

`story`, `epic`, `target_env`, `preexisting`, `operator_mode`, `phase` and `spec_nodes`
are checkpointed inputs. The `workspace` name is ambient and follows the run; `target_env` defaults to `local`, `operator_mode` defaults to `auto`, and `phase` defaults to `build`. `spec_nodes` carries the nodes the spec pass wrote, and is empty when it wrote none.

The stages, in order: [setup](#setup), [context-classification](#context-classification), [own-the-book](#own-the-book), [grounding-gate](#grounding-gate), [operator-block](#operator-block).

The flow starts when the configured story slug resolves to a readable story before any documentation turn; or when the repository has a usable OKF book and a classified documentation context.
It ends in one of these ways: a passing grounding gate returns a passed result containing every node authored during the flow; an absent OKF book returns not-applicable without an agent turn; an unusable OKF book fails before documentation; an epic-scoped operator answer returns a blocked result carrying the answer.

## Steps

### setup

- kind: prepare

The flow resolves workspace directories and prepares the requested story. An empty or
unresolvable story path raises a workflow failure before OKF detection or an agent turn. Every
entry resets the story's documentation conversation so a resume or post-fix pass cannot reuse a
conversation describing an older book. Every terminal return resets it too. The spec phase keeps
its own conversation, apart from the build phase's, because the two passes see different books.

`Docs.labels` exposes the resolved story slug as the `work_id` activity label when one exists.
`Docs.state_labels` adds the lap, block and number counters carried in the state.

### context-classification

- kind: prepare

In the spec phase the flow ensures the OKF book and goes straight to the owner turn. There is no
diff yet, so it classifies no context, resolves no story sources and builds no grounding
worklist.

In the build phase the flow first ensures the OKF book. A repository with no configured OKF graph and no services
tree gets its book root created; an unusable graph is a workflow failure. It then classifies the
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

One high-power owner turn runs in the story's documentation conversation with no timeout. The
build phase runs `document-story`. It receives the story, epic, services root, implementation
plan summary, context mode, the grounding worklist, the nodes the spec pass wrote, the last gate
report and the last operator answer. The spec phase runs `specify-story`. It receives the story,
the epic, the docs and services roots, the last gate report and the last operator answer, and
replies with a `SpecResult`. In both phases the turn writes the book and has its subagents review
and repair it. It returns `documented`, `not_required`, or a
blocked result. `not_required` still proceeds to the grounding gate. It means the story changes
nothing represented by the book, not that the gate is skipped. A blocked result goes to the
operator-block step.

The returned node identities are appended to the accumulated identities with duplicates removed.
A repair lap can therefore return an empty node list without discarding nodes authored earlier.

### grounding-gate

- kind: verify

In the spec phase the gate is the semantic route with no packet: `verify_story_documentation`
checks the author's status and that `doctor` reports no error on the nodes the owner wrote, and
nothing is grounded against code.

For local context the owner refreshes the OKF packet and runs `ostler qa compile-gaps` before
returning, scoped to every page it edited and every spec-pass page. The flow rebuilds that packet
against the post-author worktree, validates it, and asks `verify_story_documentation` to check
every changed production unit directly against the accumulated authored nodes. Semantic context
passes empty strings for both statuses. In the build phase, when the packet built, the flow also
compiles the book into a QA plan through `compile_gaps`, which shares the writer command's defect
policy, page scope and line format. Every defect gap on a page the story touched, meaning a page
of the nodes the owner authored or the spec pass wrote, fails the gate. A discharged precondition
and a node's own `:contract` or `:end-state` placeholder with no check are no defect. The gaps
reach the owner in the same report as any other failure, as lines of
`<code> <obligation>: <message>`, and spend a lap. The spec phase never runs the compile.

Once the gate holds in the build phase, local context and a built packet, the flow exercises the
book. Unless `<spec_dir>/qa_plan.py` already stands, which means QA has visited and owns its plan,
it compiles the story's QA plan from the book, leases a copy of the stack as `docs`, brings it up
and runs the plan with the label `docs-exercise`. The labelled run writes its ledger under
`<spec_dir>/qa/docs-exercise/`, so QA's scored log stays untouched. The flow releases the copy and
deletes `qa_plan.py` afterwards in every branch, so QA's preflight compiles the plan again from
the final book. A compile that yields no plan and a stack that is not up leave the gate as it was.
A run that ends in any status but `passed` or `failed`, and a `failed` run that names no scenario,
turn the gate invalid with an `E:exercise-<status>` failure and a note that the compiled plan could
not run, carrying the run's own message. That failure takes the ordinary lap route and not the
one-bounce route, so it spends a lap and parks at `MAX_LAPS` like any other red check. A failing run turns the gate invalid
once, with one `X:<scenario id>` failure per failed scenario and a report that begins
`Exercise:`, one bullet per scenario with its failed assertions. The owner repairs the claim on
its page, and that bounce is one lap. A second failing run passes: QA owns what still fails,
because a product defect belongs to dev and not to the writer.
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
build-phase owner turn. `_spec_brief` renders the story, epic and book roots for the spec phase,
which has no plan summary or classified context to read. `_context_mode` treats a manifest-resolved external source repository as locally
verifiable when the resolved story sources are present, and otherwise preserves the classifier's
local or semantic mode. `_epic_path` derives the parent epic path through configured docs-root
resolution. The module exports only `Docs`.
