---
type: flow
slug: author-story-split
title: Author story split
---
# Author story split

The [author story-split subflow](../concepts/story-split-subflow.md) decomposes one explicitly
named epic into a set of stories, then validates that the stories are complete and granular enough
to deliver the epic's scope. It operates two autonomous retry budgets, one for rework after PM findings and one for PM answers
to the splitter's questions, bounded at 3 and 2 respectively. Past either budget the split returns
blocked and the Author flow keeps the epic's row blocked for the completion gate. A passing review
is recorded as a PM receipt.

The [workhorse-author run command](../workhorse-author.md#run) selects this flow from the
[author workflow composition root](../concepts/author-workflow-composition-root.md).

- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- steps:
  - [run](../workhorse-author.md#run)
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-author.dot")
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [author story-split subflow](../concepts/story-split-subflow.md)
- detail: [story-split prompt](../formats/story-split-prompt.md)
- detail: [author PM review](../concepts/author-pm-review.md)
- detail: [PM receipt](../formats/pm-receipt.md)
- tests: `workflows/tests/author/story_split/test_flow.py::test_accepts_one_epic_graph_without_selecting_authoring_or_git`

The flow starts when the Author flow supplies an existing epic slug, or when an operator runs the standalone flow on one.
It ends in one of these ways: the epic is decomposed into stories that cover its seeds, each story names its services, the PM passes every angle and a receipt is written; or the split returns blocked with the findings or question that stopped it.

The stages, in order: [split-stories](#split-stories), [check-coverage](#check-coverage), [review](#review), [done](#done).

## Split stories

Invokes an agent against the story-split prompt to decompose the epic into stories. The agent
reads the epic's seeds, the PM ledger and any note, then uses `ostler create story` to record each
story with its seed coverage and dependency blockers.

The split result can be `complete`, `standoff`, or `blocked`:

- `complete` proceeds to the coverage check.
- `blocked` or `standoff` sends the agent's question to the PM, which answers in the ledger. The
  agent then splits again with the answer as a note. After two answers the split returns blocked.

- kind: run
- run: invoke split-stories agent, read rework notes and the PM ledger, record stories via ostler
- verify: [split_stories](../concepts/story-split-subflow.md#split_stories)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.split_stories` @9e26ab4671cb

## Check coverage

Derives each story's services from its covered seeds, then validates seed coverage, story services
and graph integrity mechanically. Errors go back to the splitter as rework notes, up to three
times.

- kind: verify
- run: derive each story's `services` from its covered seeds, then validate seed coverage, story services and graph integrity
- verify: [check_coverage](../concepts/story-split-subflow.md#check_coverage)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.check_coverage` @9e26ab4671cb

## Review

Hands the epic directory to the [PM review](../concepts/author-pm-review.md) at the `story-split`
stage. A pass on every angle accepts the split. Findings go back to the splitter as rework notes
and count against the same three reworks.

- kind: verify
- run: PM review of the story split with the previous findings
- verify: [review](../concepts/story-split-subflow.md#review)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.review` @9e26ab4671cb

## Done

A passing review has written a [PM receipt](../formats/pm-receipt.md) in the epic directory. It
binds the active seed ids and each story's slug, title, covers and dependencies, so later prose
edits keep the pass.

- kind: run
- run: accept the split whose receipt the PM review wrote
- verify: [review](../concepts/story-split-subflow.md#review)
- verify: created(subject="pm-receipt.json")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.review` @9e26ab4671cb
