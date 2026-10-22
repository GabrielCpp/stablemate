---
type: format
slug: author-split-epics-prompt
title: Author split-epics prompt
---
# Author split-epics prompt

The epic-split flow renders this template for its initial milestone-to-skeleton conversion turn. It directs the agent to read the approved milestone, the grill records in its `grills/` folder, its mockups, and the design notes it links, then create an ordered list of empty epic skeleton documents—one per coherent user journey in the milestone. The agent must use Ostler to allocate epic ids and leave every new skeleton bare: title plus empty `## Seeds` and `## Stories` sections, with no prose, seeds, or stories. The expected response is a JSON object with `status` set to `complete` or `blocked` and a `notes` value describing the skeleton list or the blocking question.

- file: `workflows/src/workhorse_workflows/author/epic_split/prompts/split-epics.md`
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.start` @978c83a852f4
- detail: [author epic-split subflow](../concepts/author-epic-split-subflow.md)
- detail: [epic split result](epic-split-result.md)
- tests: `workflows/tests/author/epic_split/test_flow.py::test_creates_only_ordered_epic_skeletons_after_review_rework`

## Fields

### milestone
- type: `str`
- required: true
- semantics: path to the approved milestone document, containing the `epics:` list to be replaced
- verify: json_path(path="$.milestone", equals="example milestone")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args` @978c83a852f4
- detail: [epic split prompt args](../concepts/epic-split-prompt-args.md)

### epics_dir
- type: `str`
- required: true
- semantics: canonical directory path where new epic skeleton documents are created
- verify: json_path(path="$.epics_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args` @978c83a852f4
- detail: [epic split prompt args](../concepts/epic-split-prompt-args.md)

### review_notes
- type: `str`
- default: empty string on initial split, populated with review findings on rework
- required: false
- semantics: feedback from the review turn applied to the split, empty on the first invocation
- verify: json_path(path="$.review_notes", equals="")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args` @978c83a852f4
- detail: [epic split prompt args](../concepts/epic-split-prompt-args.md)

## Response

### status
- type: literal `complete` or `blocked`
- required: true
- semantics: whether the agent created the ordered skeleton list or encountered a blocking product decision
- verify: json_path(path="$.status", matches="^(complete|blocked)$")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitResult` @ff0a56666e46
- detail: [epic split result](epic-split-result.md)

### notes
- type: `str`
- required: true
- semantics: description of the ordered skeleton list and its rationale, or the blocking question
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitResult` @ff0a56666e46
- detail: [epic split result](epic-split-result.md)

