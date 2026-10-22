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

The subflow snapshots the selected milestone and existing graph and delegates skeleton creation to
an agent turn. A deterministic lint then checks that only the selected milestone and new skeletons
changed. The [product manager review](author-pm-review.md) judges the result from four angles. A
failed lint or review sends its findings back to a rework turn, at most three times. A writer that
blocks puts its question to the [product manager](author-pm-gap-answer.md), at most twice. Past
either cap the subflow returns a blocked result and the Author flow asks the operator. A passing
review writes a [PM receipt](../formats/pm-receipt.md) beside the milestone. A successful split
does not commit, author prose, or create seeds or stories.

- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit` @978c83a852f4 @0
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.start` @978c83a852f4 @0
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.check` @978c83a852f4 @0
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.review` @978c83a852f4 @0
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.rework` @978c83a852f4 @0
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.ask_pm` @978c83a852f4 @0
- code: `workflows/src/workhorse_workflows/author/epic_split/nodes/_blueprint.py::blueprint` @3578fa081522 @0
- tests: `workflows/tests/author/epic_split/test_flow.py::test_creates_only_ordered_epic_skeletons_after_review_rework`
- tests: `workflows/tests/author/epic_split/test_flow.py::test_a_blocked_writer_is_answered_by_the_pm_and_retried`
- detail: [epic split context](../formats/epic-split-context.md)
- detail: [epic split result](../formats/epic-split-result.md)
- detail: [epic split validation](../formats/epic-split-validation.md)
- detail: [author split-epics prompt](../formats/author-split-epics-prompt.md)
- detail: [author rework-epic-split prompt](../formats/author-rework-epic-split-prompt.md)
- detail: [PM review angles](author-pm-angles.md)

## Fields

### note
- type: string
- default: empty
- required: false
- semantics: the operator's or the PM's answer to an earlier blocked split, given to the split turn as `note`
- verify: json_path(path="$.note", equals="")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit` @978c83a852f4 @0

## Methods

### blueprint
- sig: `Blueprint("author-epic-split") -> Blueprint`
- does: provides the registration target for deterministic epic-split nodes
- returns: returns a blueprint named `author-epic-split`
- verify: json_path(path="$.name", equals="author-epic-split")
- code: `workflows/src/workhorse_workflows/author/epic_split/nodes/_blueprint.py::blueprint` @3578fa081522 @0

### setup
- sig: `setup() -> EpicSplitContext`
- does: prepares the approved milestone and snapshots the existing planning graph
- returns: returns the [epic split context](../formats/epic-split-context.md) used by later states
- verify: count(subject="prepared epic-split contexts", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.setup` @978c83a852f4 @0

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the milestone's folder name as `work_id`
- returns: returns a `work_id` derived from the milestone's folder name
- verify: json_path(path="$.work_id", equals="CASE-1234")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.labels` @978c83a852f4 @0

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: adds epic-split budget labels to the run labels
- returns: returns labels containing `reworks` and `answers` counters
- verify: json_path(path="$.reworks", equals="example reworks")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.state_labels` @978c83a852f4 @0

### start
- sig: `start(note: str = "", answers: int = 0) -> Continue | Done`
- does: asks a high-power agent to create the milestone's ordered epic skeletons
- verify: count(subject="epic-split planning turns", equals=1)
- does: runs the split agent from the repository root with the milestone, the epics directory, the note and the PM ledger
- verify: count(subject="epic-split agent arguments", equals=1)
- does: when the writer reports `blocked`, puts its notes to the PM as a question
- verify: count(subject="epic-split questions put to the PM", equals=1)
- returns: returns a continuation targeting `check` with the split result
- verify: json_path(path="$.next_state", equals="check")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.start` @978c83a852f4 @0

### check
- sig: `check(reworks: int = 0, answers: int = 0, prior: str = "") -> Continue | Done`
- does: validates the split result deterministically before any review
- verify: json_path(path="$.ok", equals=True)
- does: when validation fails, sends its errors to `rework` as the notes
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- returns: returns a continuation targeting `review` when validation passes
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.check` @978c83a852f4 @0

### review
- sig: `review(reworks: int = 0, answers: int = 0, prior: str = "") -> Continue | Done`
- does: hands the milestone to the [PM review](author-pm-review.md) at the `epic-split` stage
- verify: count(subject="epic-split review turns", equals=1)
- does: when every angle passes, validates once more and returns an accepted result with the ordered epics
- verify: json_path(path="$.status", equals="accepted")
- does: when an angle fails, sends the findings to `rework` and keeps them as the prior findings for the next review
- verify: count(subject="epic-split rework continuations", equals=1)
- returns: returns `Done` only after validation and the review pass, otherwise a rework continuation or a blocked result
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.review` @978c83a852f4 @0

### rework
- sig: `rework(notes: str, note: str = "", reworks: int = 0, answers: int = 0, prior: str = "") -> Continue | Done`
- does: sends the findings to a high-power agent turn that corrects the epic skeletons
- does: runs the rework agent from the repository root with the findings, the note and the PM ledger
- does: increments the rework count before returning to `check`
- does: when three reworks have run, returns a blocked result carrying the last findings
- verify: json_path(path="$.status", equals="blocked")
- returns: returns a continuation targeting `check` with the incremented rework count
- verify: count(subject="epic-split rework turns", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.rework` @978c83a852f4 @0

### ask_pm
- sig: `ask_pm(question: str, phase: str, notes: str = "", reworks: int = 0, answers: int = 0, prior: str = "") -> Continue`
- does: hands the writer's question to the [gap answer](author-pm-gap-answer.md) flow with the asker `epic-split`
- verify: count(subject="epic-split gap answers", equals=1)
- does: retries the writer that asked, with the answer as its `note`
- does: increments the answer count; at two answers a further question returns a blocked result
- returns: returns a continuation targeting `start` or `rework` according to the phase that asked
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.ask_pm` @978c83a852f4 @0

### _split_args
- sig: `_split_args(review_notes: str = "", note: str = "") -> dict[str, str]`
- does: builds the agent arguments from the prepared milestone and epic-directory paths
- does: includes the review notes, the combined note and the PM ledger path
- verify: json_path(path="$.review_notes", equals="")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args` @978c83a852f4 @0

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
- code: `workflows/src/workhorse_workflows/author/epic_split/nodes/epics.py::prepare_epic_split` @f98938ce7adf

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
- code: `workflows/src/workhorse_workflows/author/epic_split/nodes/epics.py::validate_epic_split` @f98938ce7adf
