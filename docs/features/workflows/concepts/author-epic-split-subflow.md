---
type: concept
slug: author-epic-split-subflow
title: Author epic split subflow
---
# Author epic split subflow

The `epic_split` package is the named author subflow that converts one approved roadmap-owned
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

- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit`
- code: `workflows/src/workhorse_workflows/author/epic_split/nodes/_blueprint.py::blueprint`
- tests: `workflows/tests/author/epic_split/test_flow.py::test_creates_only_ordered_epic_skeletons_after_review_rework`
- detail: [epic split context](../epic-split-context.md)
- detail: [epic split result](../epic-split-result.md)
- detail: [epic split review](../epic-split-review.md)
- detail: [epic split validation](../epic-split-validation.md)
- detail: [operator resolution](../operator-resolution.md)

## Fields

### operator_mode
- type: literal `auto` or `human`
- default: `auto` — unresolved work is automatically diagnosed before the operator gate
- required: true
- semantics: `human` sends exhausted or blocked review directly to the operator context
- semantics: `auto` permits up to two resolution turns before the operator context
- verify: json_path(path="$.operator_mode", equals="auto")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit`

## Methods

### blueprint
- sig: `Blueprint("author-epic-split") -> Blueprint`
- does: provides the registration target for deterministic epic-split nodes
- returns: returns a blueprint named `author-epic-split`
- verify: json_path(path="$.name", equals="author-epic-split")
- code: `workflows/src/workhorse_workflows/author/epic_split/nodes/_blueprint.py::blueprint`

### setup
- sig: `setup() -> EpicSplitContext`
- does: prepares the approved roadmap milestone and snapshots the existing planning graph
- returns: returns the [epic split context](../epic-split-context.md) used by later states
- verify: count(subject="prepared epic-split contexts", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.setup`

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the roadmap filename stem as `work_id`
- returns: returns a `work_id` derived from the roadmap path stem
- verify: json_path(path="$.work_id", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.labels`

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: adds epic-split budget labels to the run labels
- returns: returns labels containing `reworks` and `resolves` counters
- verify: json_path(path="$.reworks", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.state_labels`

### start
- sig: `start(resolves: int = 0) -> Continue`
- does: asks a high-power agent to create the milestone's ordered epic skeletons
- does: runs the split agent from the repository root
- does: passes the roadmap, milestone, epic-directory, and empty review-notes arguments
- returns: returns a continuation targeting `review` with the split result
- verify: count(subject="epic-split planning turns", equals=1)
- verify: json_path(path="$.next_state", equals="review")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.start`

### review
- sig: `review(reworks: int = 0, resolves: int = 0) -> Continue | Await | Done`
- does: asks a high-power independent agent to review the ordered epic skeletons
- verify: count(subject="epic-split review turns", equals=1)
- does: validates an approved review before completing
- verify: json_path(path="$.ok", equals=True)
- does: passes validation errors back as review notes when an approved review fails validation
- verify: json_path(path="$.notes", matches=".+")
- does: sends a non-blocked review failure to rework while fewer than three reworks have occurred
- verify: count(subject="epic-split rework continuations", equals=1)
- does: sends blocked or rework-exhausted review work to automatic resolution while automatic resolution remains available
- verify: count(subject="epic-split resolution turns", equals=1)
- does: sends blocked or exhausted review work to the operator gate in human mode or after two resolutions
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: sends a non-blocked review to the operator gate after the rework and resolution budgets are exhausted
- verify: visible(locator="operator-awaiting context", text="blocked")
- returns: returns `Done` only after validation succeeds, otherwise a rework or await continuation
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.review`
- when: the review status is `approved`, validates the split result before completing
- when: an approved review fails deterministic validation, replaces the review notes with the validation errors
- when: the review status is not `blocked` and fewer than three reworks have occurred, continues to `rework`
- when: the review is blocked, or three reworks are exhausted, while operator mode is `auto` and fewer than two resolutions have occurred, continues to `resolve`
- when: operator mode is `human` or two automatic resolutions have occurred, continues to the operator gate
- when: a non-blocked review has exhausted three reworks and automatic resolution is unavailable, continues to the operator gate

### rework
- sig: `rework(notes: str, reworks: int = 0, resolves: int = 0) -> Continue`
- does: sends review notes to a high-power agent turn that corrects the epic skeletons
- does: runs the rework agent from the repository root with the current roadmap and milestone context
- does: increments the rework count before returning to review
- returns: returns a continuation targeting `review` with the incremented rework count
- verify: count(subject="epic-split rework turns", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.rework`

### resolve
- sig: `resolve(notes: str, resolves: int = 0) -> Await`
- does: asks an unbounded-timeout resolver agent to diagnose an unresolved split decision
- does: supplies the operator context path and block notes to the resolver
- does: parks the flow at the operator context after the resolver returns
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: increments the resolution count on the continuation that restarts splitting
- returns: returns an operator-awaiting continuation with the incremented resolution count
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve`

### _context_path
- sig: `_context_path() -> Path`
- does: resolves the author operator-context path beneath the workflow repository root
- verify: json_path(path="$.context_path", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._context_path`

### _split_args
- sig: `_split_args(review_notes: str = "") -> dict[str, str]`
- does: builds the agent arguments from the prepared roadmap, milestone, and epic-directory paths
- does: includes the supplied review notes and defaults them to an empty string
- verify: json_path(path="$.review_notes", equals="")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args`

## Nodes

### prepare_epic_split
- sig: `prepare_epic_split(logger: logging.Logger, repo_dir: str = "") -> EpicSplitContext`
- does: resolves the repository root from the optional repository directory
- verify: count(subject="epic-split repository resolutions", equals=1)
- does: requires the approved roadmap to source exactly one milestone and no other source
- verify: count(subject="roadmap-owned epic-split milestones", equals=1)
- does: snapshots milestone documents, epic documents, seed identities, and story identities
- verify: created(subject="an epic-split graph snapshot")
- returns: returns the [epic split context](../epic-split-context.md) bounding later mutations
- code: `workflows/src/workhorse_workflows/author/epic_split/nodes/epics.py::prepare_epic_split`

### validate_epic_split
- sig: `validate_epic_split(logger: logging.Logger, context: EpicSplitContext) -> EpicSplitValidation`
- does: requires exactly one milestone sourced solely by the prepared roadmap
- verify: json_path(path="$.ok", equals=True)
- does: requires a non-empty ordered milestone epic list without duplicate normalized slugs
- verify: unchanged(subject="ordered milestone epics", except_fields=[])
- does: requires every milestone epic to have an epic skeleton
- verify: count(subject="milestone epics with skeletons", equals=1)
- does: rejects changes to prepared seeds, stories, unrelated milestones, and existing epics
- verify: unchanged(subject="pre-existing planning graph", except_fields=[])
- does: rejects prose, seeds, or stories inside a newly created epic skeleton
- verify: absent(subject="authored content inside new epic skeletons")
- returns: returns validation status, milestone path, ordered epics, and newline-separated errors
- code: `workflows/src/workhorse_workflows/author/epic_split/nodes/epics.py::validate_epic_split`
