---
type: flow
slug: author-story-split
title: Author story split
---
# Author story split

The [author story-split subflow](../concepts/story-split-subflow.md) decomposes one explicitly
named epic into a set of stories, then validates that the stories are complete and granular enough
to deliver the epic's scope. It operates two autonomous retry budgets — one for story-split agent
reworks and one for split-decision resolution — bounded at 3 and 2 respectively, above which work
escalates to an operator gate. A passing review is recorded as a digest-bound receipt.

The [workhorse-author run command](../workhorse-author.md#run) selects this flow from the
[author workflow composition root](../concepts/author-workflow-composition-root.md).

- start: an operator supplies an existing epic slug and selects `operator_mode` of `auto` or `human`
- start: the epic's directory is resolvable under the configured Ostler graph
- start: the epic has not already been split (or resumes a prior split with coverage findings to address)
- steps:
  - [split-stories](#split-stories)
  - [check-coverage](#check-coverage)
  - [done](#done)
- end: the epic is decomposed into stories with each story covering one or more seeds
- end: story granularity is reviewed as adequate for independent implementation and QA
- end: a passing split and review is recorded in a digest-bound receipt
- end: unresolved product or sequencing decisions are parked at an operator gate
- verify: created(subject="story-split receipt")
- verify: emitted(event="story-split completes", count=1)
- verify: json_path(path="$.epic", matches=".+")
- detail: [author story-split subflow](../concepts/story-split-subflow.md)
- detail: [story-split prompt](../story-split-prompt.md)
- detail: [coverage review prompt](../coverage-review-prompt.md)
- tests: `workflows/tests/author/story_split/test_flow.py::test_accepts_one_epic_graph_without_selecting_authoring_or_git`

## Split stories

Invokes an agent against the story-split prompt to decompose the epic into stories. The agent
reads the epic's researched seeds, user journeys, and acceptance criteria, then uses `ostler
create story` to record each story under the epic's `## Stories` section with its seed coverage
and dependency blockers recorded.

The split result can be `complete`, `standoff`, or `blocked`:

- `complete` — the split is recorded; proceed to coverage review. If rework notes exist from a
  prior coverage failure, the agent addresses them in this pass.
- `standoff` — the agent refuses rework notes from a prior coverage failure, judging the change
  wrong. This escalates to the operator at the `_gate_coverage` decision point.
- `blocked` — the agent raises a product decision question. If `operator_mode` is `auto` and
  `split_resolves` < 2, the flow calls `resolve_split` to query the resolver agent; otherwise
  this escalates to the operator gate.

After a successful split, the flow invokes `ostler doctor --epic` to confirm the graph is acyclic,
every seed is covered, and no edge references another epic.

- kind: run
- run: invoke split-stories agent, read rework notes from prior coverage failures, record stories via ostler
- verify: [split_stories](../concepts/story-split-subflow.md#split_stories)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.split_stories`

## Check coverage

Validates the split stories against the epic's scope. Two sequential steps: first, a deterministic
mechanical check confirms every seed is claimed and the dependency graph is acyclic; second, a
high-power agent reviews the stories for adequacy — whether they are granular and complete enough
to implement and QA independently.

The review result can be `ok`, `gaps`, or `blocked`:

- `ok` — stories cover the epic adequately; record the receipt and finish.
- `gaps` — the reviewer identifies under-covered scope or coarse stories. This loops back to
  `split_stories` with the reviewer's notes, reworking the split up to 3 times.
- `blocked` — the reviewer raises a product decision. If `operator_mode` is `auto` and
  `split_resolves` < 2, the flow calls `resolve_coverage`; otherwise this escalates to the
  operator gate.

- kind: verify
- run: validate seed coverage and graph integrity; invoke coverage-review agent
- verify: [check_coverage](../concepts/story-split-subflow.md#check_coverage)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.check_coverage`
- detail: [story-split check-coverage step roles](../concepts/story-split-check-coverage-step-roles.md)

## Done

Records a digest-bound receipt of the split and review when coverage review passes. The receipt is
recorded under the epic's `story-split-receipt.json` and captures the exact story digest.

- kind: run
- run: record the split and review receipt with the exact story digest
- verify: [check_coverage](../concepts/story-split-subflow.md#check_coverage)
- verify: created(subject="story-split-receipt.json")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.check_coverage`
- detail: [story-split check-coverage step roles](../concepts/story-split-check-coverage-step-roles.md)

