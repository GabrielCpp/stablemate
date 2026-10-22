---
type: concept
slug: author-epic-split-subflow
title: Author epic split subflow
---
# Author epic split subflow

The `epic_split` package is the named author subflow that converts one approved
milestone into an ordered list of empty epic skeletons. It deliberately stops at the epic
boundary: it neither authors epic prose nor creates seeds or stories. The [author workflow
composition root](author-workflow-composition-root.md) registers this machine alongside the other
author stages.

The subflow snapshots the selected milestone and existing graph, delegates skeleton creation and
review to agent turns, validates that only the selected milestone and new skeletons changed, and
parks blocked or exhausted work at the operator context. Its deterministic nodes are registered
on the package-local blueprint. The `operator_mode` field defaults to `auto`; automatic resolution
is limited to two turns, and review rework is limited to three turns. Human operator mode bypasses
automatic resolution. A successful split does not commit, author prose, or create seeds or stories.

- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit` @3bce606b747d
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.start` @3bce606b747d
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.review` @3bce606b747d
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.rework` @3bce606b747d
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve` @3bce606b747d
- code: `workflows/src/workhorse_workflows/author/epic_split/nodes/_blueprint.py::blueprint` @3578fa081522
- tests: `workflows/tests/author/epic_split/test_flow.py::test_creates_only_ordered_epic_skeletons_after_review_rework`
- detail: [epic split context](../formats/epic-split-context.md)
- detail: [epic split result](../formats/epic-split-result.md)
- detail: [epic split review](../formats/epic-split-review.md)
- detail: [epic split validation](../formats/epic-split-validation.md)
- detail: [operator resolution](../formats/operator-resolution.md)
- detail: [author split-epics prompt](../formats/author-split-epics-prompt.md)
- detail: [author review-epic-split prompt](../formats/author-review-epic-split-prompt.md)
- detail: [author rework-epic-split prompt](../formats/author-rework-epic-split-prompt.md)
- detail: [author resolve-epic-split prompt](../formats/author-resolve-epic-split-prompt.md)
- detail: [epic split resolve documentation scope](epic-split-resolve-documentation-scope.md)

## Fields

### operator_mode
- type: literal `auto` or `human`
- default: `auto` — unresolved work is automatically diagnosed before the operator gate
- required: true
- semantics: `human` sends exhausted or blocked review directly to the operator context
- semantics: `auto` permits up to two resolution turns before the operator context
- verify: json_path(path="$.operator_mode", equals="auto")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit` @3bce606b747d

## Methods

### blueprint
- sig: `Blueprint("author-epic-split") -> Blueprint`
- does: provides the registration target for deterministic epic-split nodes
- returns: returns a blueprint named `author-epic-split`
- verify: json_path(path="$.name", equals="author-epic-split")
- code: `workflows/src/workhorse_workflows/author/epic_split/nodes/_blueprint.py::blueprint` @3578fa081522

### setup
- sig: `setup() -> EpicSplitContext`
- does: prepares the approved milestone and snapshots the existing planning graph
- returns: returns the [epic split context](../formats/epic-split-context.md) used by later states
- verify: count(subject="prepared epic-split contexts", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.setup` @3bce606b747d

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the milestone's folder name as `work_id`
- returns: returns a `work_id` derived from the milestone's folder name
- verify: json_path(path="$.work_id", equals="CASE-1234")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.labels` @3bce606b747d

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: adds epic-split budget labels to the run labels
- returns: returns labels containing `reworks` and `resolves` counters
- verify: json_path(path="$.reworks", equals="example reworks")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.state_labels` @3bce606b747d

### start
- sig: `start(resolves: int = 0) -> Continue`
- does: asks a high-power agent to create the milestone's ordered epic skeletons
- verify: count(subject="epic-split planning turns", equals=1)
- does: runs the split agent from the repository root
- verify: count(subject="epic-split agent runs from the repository root", equals=1)
- does: passes the milestone, epic-directory, and empty review-notes arguments
- verify: count(subject="epic-split agent arguments", equals=1)
- returns: returns a continuation targeting `review` with the split result
- verify: json_path(path="$.next_state", equals="review")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.start` @3bce606b747d

### review
- sig: `review(reworks: int = 0, resolves: int = 0) -> Continue | Await | Done`
- does: asks a high-power independent agent to review the ordered epic skeletons
- verify: count(subject="epic-split review turns", equals=1)
- does: when the review status is `approved`, validates the split result before completing
- verify: json_path(path="$.ok", equals=True)
- does: when an approved review fails deterministic validation, replaces the review notes with the validation errors
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- does: when the review status is not `blocked` and fewer than three reworks have occurred, continues to `rework`
- verify: count(subject="epic-split rework continuations", equals=1)
- does: when the review is blocked, or three reworks are exhausted, while operator mode is `auto` and fewer than two resolutions have occurred, continues to `resolve`
- verify: count(subject="epic-split resolution turns", equals=1)
- does: when operator mode is `human` or two automatic resolutions have occurred, continues to the operator gate
- verify: json_path(path="$.await", matches="blocked")
- does: when a non-blocked review has exhausted three reworks and automatic resolution is unavailable, continues to the operator gate
- returns: returns `Done` only after validation succeeds, otherwise a rework or await continuation
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.review` @3bce606b747d

### rework
- sig: `rework(notes: str, reworks: int = 0, resolves: int = 0) -> Continue`
- does: sends review notes to a high-power agent turn that corrects the epic skeletons
- does: runs the rework agent from the repository root with the current milestone context
- does: increments the rework count before returning to review
- returns: returns a continuation targeting `review` with the incremented rework count
- verify: count(subject="epic-split rework turns", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.rework` @3bce606b747d

### resolve
- sig: `resolve(notes: str, resolves: int = 0) -> Await`
- does: asks an unbounded-timeout resolver agent to diagnose an unresolved split decision
- does: supplies the operator context path and block notes to the resolver
- does: parks the flow at the operator context after the resolver returns
- verify: json_path(path="$.await", matches="blocked")
- does: increments the resolution count on the continuation that restarts splitting
- returns: returns an operator-awaiting continuation with the incremented resolution count
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve` @3bce606b747d

### _context_path
- sig: `_context_path() -> Path`
- does: resolves the author operator-context path beneath the workflow repository root
- verify: json_path(path="$.context_path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._context_path` @3bce606b747d

### _split_args
- sig: `_split_args(review_notes: str = "") -> dict[str, str]`
- does: builds the agent arguments from the prepared milestone and epic-directory paths
- does: includes the supplied review notes and defaults them to an empty string
- verify: json_path(path="$.review_notes", equals="")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args` @3bce606b747d

## Nodes

### prepare_epic_split
- sig: `prepare_epic_split(logger: logging.Logger, repo_dir: str = "") -> EpicSplitContext`
- does: resolves the repository root from the optional repository directory
- verify: count(subject="epic-split repository resolutions", equals=1)
- does: requires exactly one approved milestone that passes its readiness check
- verify: count(subject="approved epic-split milestones", equals=1)
- does: snapshots milestone documents, epic documents, seed identities, and story identities
- verify: created(subject="an epic-split graph snapshot")
- consistency: epic-split-context — returns the [epic split context](../formats/epic-split-context.md) with the selected milestone path to bound later mutations
- verify: json_path(path="$.milestone_path", equals="docs/milestones/account-access/milestone.md")
- code: `workflows/src/workhorse_workflows/author/epic_split/nodes/epics.py::prepare_epic_split` @868f7136431c

### validate_epic_split
- sig: `validate_epic_split(logger: logging.Logger, context: EpicSplitContext) -> EpicSplitValidation`
- does: requires the prepared milestone path to still resolve to exactly one milestone
- verify: json_path(path="$.ok", equals=True)
- does: requires a non-empty ordered milestone epic list without duplicate normalized slugs
- verify: unchanged(subject="ordered milestone epics", except_fields=[])
- does: requires every milestone epic to have an epic skeleton
- verify: count(subject="milestone epics with skeletons", equals=1)
- consistency: seed-identities — rejects mutations to seed identities captured in the prepared context
- verify: json_path(path="$.errors", matches=".*must not create, remove, or edit seeds in '.+'.*")
- consistency: story-identities — rejects mutations to story identities captured in the prepared context
- verify: json_path(path="$.errors", matches=".*must not create, remove, or edit stories in '.+'.*")
- consistency: milestone-documents — rejects mutations to milestone documents other than the selected milestone
- verify: json_path(path="$.errors", matches=".*must not edit unrelated milestone '.+'.*")
- consistency: epic-documents — rejects mutations to pre-existing epic documents
- verify: json_path(path="$.errors", matches=".*must not edit existing epic '.+'.*")
- does: rejects prose, seeds, or stories inside a newly created epic skeleton
- verify: absent(subject="authored content inside new epic skeletons")
- returns: returns validation status, milestone path, ordered epics, and newline-separated errors
- code: `workflows/src/workhorse_workflows/author/epic_split/nodes/epics.py::validate_epic_split` @868f7136431c
