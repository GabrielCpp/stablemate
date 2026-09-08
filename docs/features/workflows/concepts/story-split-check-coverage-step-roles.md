---
type: concept
slug: story-split-check-coverage-step-roles
title: Story-split check-coverage step roles
---
# Story-split check-coverage step roles

The [author story-split flow](../flows/author-story-split.md)'s `check-coverage` and `done`
sections both ground themselves in `StorySplitFlow.check_coverage` because that one method
implements both: it is a single state-machine transition that decides an outcome and, on the
passing outcome, immediately produces the terminal effect. There is no second implementation
to choose between — `check-coverage` documents the decision half (mechanical seed/graph
validation, then the semantic coverage-review agent turn) and `done` documents the effect half
(recording the digest-bound receipt and returning `StorySplitDone`) that the same call performs
once that decision comes back `ok`.

The receipt write itself is delegated one level further, to
`record_story_split_review`, which `check_coverage` calls only on the `ok` path; `done`
describes that delegated effect as part of the one transition that triggers it, not as a
competing entry point.

- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.check_coverage`
- code: `workflows/src/workhorse_workflows/author/story_split/nodes/review.py::record_story_split_review`
- rule: use `check-coverage` to read the review decision and `done` to read the terminal receipt effect it produces on success; neither section is an alternative to the other
