---
type: flow
slug: coder-review
title: Coder review flow
---
# Coder review flow

- The `Review` machine independently judges one story's implementation, applies unresolved
  findings through the implementer's conversation, and does not proceed until settlement is
  verified or an operator has resolved the block. It is entered by Coder or directly with
  `workhorse-coder run review`.
- The flow accepts a story slug plus optional docs/workspace, epic, operator mode, repository,
  branch, pull request, and inherited implementation-turn inputs. Empty repository selection
  derives affected repositories from the story plan; an explicit repository is used for a
  standalone review when no plan context exists.
- start: the configured story resolves to an existing story file and review context
- verify: count(subject="review setup contexts", equals=1)
- start: the review run has a story context and the review loop starts with inherited session turns
- verify: count(subject="review loop initializations", equals=1)
- steps:
  - [setup](#setup)
  - [feeder-review](#feeder-review)
  - [implementation-verdict](#implementation-verdict)
  - [settlement](#settlement)
  - [operator-resolution](#operator-resolution)
  - [feedback](#feedback)
- end: an approved implementation or verified settlement reaches the feedback checkpoint and returns a review result
- verify: count(subject="review result completions", equals=1)
- end: an unreadable story, blocked review, unresolvable settlement, or exhausted rework path is operator-gated rather than silently approved
- verify: count(subject="review operator-gated paths", equals=1)
- detail: [coder main flow](coder-main.md)
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review`
- tests: `workflows/tests/coder/review/test_flow.py::test_an_approved_review_stamps_the_specs_and_stops`
- tests: `workflows/tests/coder/review/test_flow.py::test_the_apply_loop_is_bounded_and_then_reaches_the_operator`
- tests: `workflows/tests/coder/review/test_flow.py::test_the_settlement_gate_overrules_an_unproven_applied_claim`
- tests: `workflows/tests/coder/review/test_flow.py::test_repeated_operator_cycles_never_give_up`
- tests: `workflows/tests/coder/review/test_flow.py::test_dropped_feedback_buys_exactly_one_rework_pass`
- tests: `workflows/tests/coder/review/test_flow.py::test_a_run_killed_mid_review_resumes_on_the_review_state`

The judging turns run cold in the docs repository with the affected code repositories granted as
additional directories. Apply turns rejoin the story-derived implementation conversation when
one exists; a standalone review therefore applies cold. The feeder review combines bug, standard,
and reuse lenses in one pass, and every finding is retained: scores at least 80 become mandatory
findings while lower scores remain advisory context.

## Steps

### setup

Workspace directories, the story path, and review context are resolved once. The story must exist
as a file or the flow raises a workflow failure before any agent turn. The resolved docs repository
is the cwd for all judging turns, and the affected code repositories come from `plan-context.json`
and the workspace manifest, or from the explicit `repo` input in standalone mode.

### feeder-review

The flow clears the previous cycle's `review-resolution.json` and `review-settlement.json`, resets
the feeder conversation, and dispatches one medium-power `code-review` turn. It passes the story
path, affected repository paths, branch, and pull request number. A blocked feeder pass means the
diff could not be read and goes to the operator path; it is never treated as an empty review.

The returned findings are carried to the next state rather than read from node output. Reuse is a
category of this same finding list, not another agent turn.

### implementation-verdict

The high-power `review-implementation` turn receives the story, plan identity, affected paths,
and two rendered finding lists. The mandatory list contains findings with confidence greater than
or equal to 80; the advisory list contains findings below 80. An `approved` verdict proceeds to
feedback. A `needs_changes` verdict supplies notes to the apply loop. A `blocked` verdict goes
directly to operator resolution because no useful apply action can be derived from it. Specs are
stamped after every verdict pass, including blocked and rework passes.

### settlement

Each apply pass dispatches the shared `apply-review` turn with review notes or operator feedback,
using the story's implementation conversation when available. The turn must write a structured
review-resolution sidecar. The deterministic settlement gate asks Ostler to verify every cited
artifact and assertion and reads the resulting settlement ledger, never trusting the turn's
self-reported status.

When every finding is verified, the flow exits the review loop without a full re-review. Missing
or incorrect proof, a malformed verdict, or no verdict sidecar produces `needs_changes` and
re-applies only what remains open. A finding reported unresolvable produces `blocked` and is
operator-gated. The local apply budget is three rework passes.

### operator-resolution

`human` and `operator` modes await an answer in the story context file immediately. In `auto`
mode, the resolver may write an answer only when it can cite an existing decision, convention, or
acceptance criterion; otherwise the flow awaits the operator. The answer is consumed from the
node output and applied as story-level feedback. A blocked application of the operator's answer
returns to the gate instead of re-reviewing unchanged code.

An operator answer returns to the feeder review with a fresh local rework budget, while the
cumulative block count remains on the `ReviewLoop`. Resolver turns are limited to three before
subsequent blocks go directly to a human; the underlying review is never abandoned.

### feedback

After approval or verified settlement, the run inbox is polled once. No outstanding message ends
the flow with `ReviewResult` so the caller can continue to QA. An outstanding message is consumed,
replied to, and applied as exactly one rework pass without passing stale review findings; the
result then returns to the implementation verdict with the existing rework allowance.

The loop carries `rework`, cumulative `blocks`, and shared implementation `session_turns` as one
checkpointed `ReviewLoop`. Session turns are seeded from `inherited_turns`, incremented by apply
passes, and recycled at eight turns. If execution stops during review, the checkpoint restores the
review verdict and loop together, resuming at the verdict state without repeating the feeder pass.
