---
type: format
slug: author-rework-epic-split-prompt
title: Author rework-epic-split prompt
---
# Author rework-epic-split prompt

The epic-split flow renders this template for each rework iteration following a review that requested repairs. It directs the agent to apply every finding from the review to the ordered epic list and its bare skeletons, then return the updated list to the review cycle. The agent must not author epic prose, seeds, stories, roadmap changes, or any downstream artifacts; it must preserve existing epic documents unchanged and focus only on repairs to the skeleton structure and order. The expected response is a JSON object with `status` set to `complete` or `blocked` and a `notes` value describing what changed or the remaining blocking question.

- file: `workflows/src/workhorse_workflows/author/epic_split/prompts/rework-epic-split.md`
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.rework`
- detail: [author epic-split subflow](concepts/author-epic-split-subflow.md)
- detail: [epic split result](epic-split-result.md)
- tests: `workflows/tests/author/epic_split/test_flow.py::test_creates_only_ordered_epic_skeletons_after_review_rework`

## Fields

### roadmap
- type: `str`
- required: true
- semantics: path to the approved roadmap document
- verify: json_path(path="$.roadmap", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args`
- detail: [epic split prompt args](concepts/epic-split-prompt-args.md)

### milestone
- type: `str`
- required: true
- semantics: path to the milestone document whose epic skeleton list requires rework
- verify: json_path(path="$.milestone", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args`
- detail: [epic split prompt args](concepts/epic-split-prompt-args.md)

### epics_dir
- type: `str`
- required: true
- semantics: canonical directory path where the epic skeleton documents are stored
- verify: json_path(path="$.epics_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args`
- detail: [epic split prompt args](concepts/epic-split-prompt-args.md)

### review_notes
- type: `str`
- required: true
- semantics: exact findings and repairs from the review turn to be applied to the skeletons
- verify: json_path(path="$.review_notes", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.rework`

## Response

### status
- type: literal `complete` or `blocked`
- required: true
- semantics: whether the agent completed all repairs or encountered a new blocking question
- verify: json_path(path="$.status", matches="^(complete|blocked)$")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitResult`
- detail: [epic split result](epic-split-result.md)

### notes
- type: `str`
- required: true
- semantics: description of what changed in the rework, or the new blocking question
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitResult`
- detail: [epic split result](epic-split-result.md)

