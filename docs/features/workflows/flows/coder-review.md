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
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.setup`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.start`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.review`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.resolve_review`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.read_operator`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply_resolved`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.poll_feedback`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply_feedback`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.labels`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.state_labels`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::MUST_FIX_CONFIDENCE`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::MAX_SESSION_TURNS`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::split_on_confidence`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::findings_block`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::require_story_file`
- tests: `workflows/tests/coder/review/test_flow.py::test_an_approved_review_stamps_the_specs_and_stops`
- tests: `workflows/tests/coder/review/test_flow.py::test_the_split_is_inclusive_at_the_confidence_line`
- tests: `workflows/tests/coder/review/test_flow.py::test_a_findings_block_says_none_rather_than_rendering_empty`
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

- kind: prepare

Workspace directories, the story path, and review context are resolved once. The story must exist
as a file or the flow raises a workflow failure before any agent turn. The resolved docs repository
is the cwd for all judging turns, and the affected code repositories come from `plan-context.json`
and the workspace manifest, or from the explicit `repo` input in standalone mode.

`Review.setup` performs this resolution and validates the story before returning the shared
`StoryPaths` context. `Review.labels` exposes the story slug as the run activity identifier, while
`Review.state_labels` adds the three `ReviewLoop` counters only after a loop exists.

The optional `branch` and `pr_number` inputs are preserved for the feeder review. `operator_mode`,
`epic`, and `inherited_turns` control later routing and session accounting. A missing or
non-file story path is rejected before any agent turn.

### feeder-review

- kind: run

The flow clears the previous cycle's `review-resolution.json` and `review-settlement.json`, resets
the feeder conversation, and dispatches one medium-power `code-review` turn. It passes the story
path, affected repository paths, branch, and pull request number. A blocked feeder pass means the
diff could not be read and goes to the operator path; it is never treated as an empty review.

The returned findings are carried to the next state rather than read from node output. Reuse is a
category of this same finding list, not another agent turn.

`split_on_confidence` sends every finding scored 80 or higher to the mandatory list and retains
every lower-scored finding in the advisory list. `findings_block` renders an empty list as
`None.`; otherwise it retains each finding's target, issue, category, confidence, and repair.

The feeder reviews only changed lines in each affected repository, considering bugs, installed
standards, local guidance, and reuse or duplication. It may inspect an open pull request for
comments, but the local working-tree or branch diff remains the review target; no pull request is
required.

### implementation-verdict

- kind: verify

The high-power `review-implementation` turn receives the story, plan identity, affected paths,
and two rendered finding lists. The mandatory list contains findings with confidence greater than
or equal to 80; the advisory list contains findings below 80. An `approved` verdict proceeds to
feedback. A `needs_changes` verdict supplies notes to the apply loop. A `blocked` verdict goes
directly to operator resolution because no useful apply action can be derived from it. Specs are
stamped after every verdict pass, including blocked and rework passes.

The implementation verdict must identify one of the three statuses; a missing status is a parse
failure and does not silently become a rework decision.

The verdict reviewer compares the story and plan with the changed repositories, folds in all
mandatory automated findings including `Reuse`, and records `review.md` plus the story's reviewed
status. Only Critical or Major findings require changes; informational or Minor findings do not
block approval.

### settlement

- kind: verify

Each apply pass dispatches the shared `apply-review` turn with review notes or operator feedback,
using the story's implementation conversation when available. The turn must write a structured
review-resolution sidecar. The deterministic settlement gate asks Ostler to verify every cited
artifact and assertion and reads the resulting settlement ledger, never trusting the turn's
self-reported status.

When every finding is verified, the flow exits the review loop without a full re-review. Missing
or incorrect proof, a malformed verdict, or no verdict sidecar produces `needs_changes` and
re-applies only what remains open. A finding reported unresolvable produces `blocked` and is
operator-gated. The local apply budget is three rework passes.

Each apply pass spends one shared implementation-session turn, writes the structured resolution
sidecar, and is judged by the settlement ledger. A verified `applied` result exits without a full
re-review. Missing, malformed, or incompletely verified proof returns only the open work to apply;
a blocked finding goes to the operator without spending another local rework pass.

An apply turn is limited to the supplied story and review findings. It must preserve the existing
story scope, update tests when behavior changes, and provide one settlement entry per required
finding with only existing artifacts or exact assertions as proof. Product decisions, broad
replanning, unavailable verification, and out-of-scope work are reported as blocked.

### operator-resolution

- kind: drive

`human` and `operator` modes await an answer in the story context file immediately. In `auto`
mode, the resolver may write an answer only when it can cite an existing decision, convention, or
acceptance criterion; otherwise the flow awaits the operator. The answer is consumed from the
node output and applied as story-level feedback. A blocked application of the operator's answer
returns to the gate instead of re-reviewing unchanged code.

An operator answer returns to the feeder review with a fresh local rework budget, while the
cumulative block count remains on the `ReviewLoop`. Resolver turns are limited to three before
subsequent blocks go directly to a human; the underlying review is never abandoned.

### feedback

- kind: run

After approval or verified settlement, the run inbox is polled once. No outstanding message ends
the flow with `ReviewResult` so the caller can continue to QA. An outstanding message is consumed,
replied to, and applied as exactly one rework pass without passing stale review findings; the
result then returns to the implementation verdict with the existing rework allowance.

The loop carries `rework`, cumulative `blocks`, and shared implementation `session_turns` as one
checkpointed `ReviewLoop`. Session turns are seeded from `inherited_turns`, incremented by apply
passes, and recycled at eight turns. If execution stops during review, the checkpoint restores the
review verdict and loop together, resuming at the verdict state without repeating the feeder pass.

The feeder session resets whenever `start` begins a review round. Apply turns use the story-derived
implementation session when one exists and otherwise run cold. The block counter survives operator
answers, the local rework counter resets only after an operator resolution returns to `start`, and
the session counter recycles at eight turns.

The state methods are deliberately split by responsibility: `Review.start` feeds findings,
`Review.review` makes the implementation verdict, `Review.apply` settles review findings,
`Review.resolve_review` and `Review.read_operator` handle the operator path, `Review.apply_resolved`
re-enters a fresh review round, and `Review.poll_feedback` plus `Review.apply_feedback` handle the
single non-blocking inbox rework pass. `MUST_FIX_CONFIDENCE` is 80 and `MAX_SESSION_TURNS` is 8;
the local rework and cumulative block ceilings are class-level routing controls on `Review`.
