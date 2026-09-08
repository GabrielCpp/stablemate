---
type: format
slug: author-split-epics-prompt
title: Author split-epics prompt
---
# Author split-epics prompt

The epic-split flow renders this template for its initial milestone-to-skeleton conversion turn. It directs the agent to read an approved roadmap and its selected milestone, then create an ordered list of empty epic skeleton documents—one per coherent user journey in the milestone. The agent must use Ostler to allocate epic ids and leave every new skeleton bare: title plus empty `## Seeds` and `## Stories` sections, with no prose, seeds, or stories. The expected response is a JSON object with `status` set to `complete` or `blocked` and a `notes` value describing the skeleton list or the blocking question.

- file: `workflows/src/workhorse_workflows/author/epic_split/prompts/split-epics.md`
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.start`
- detail: [author epic-split subflow](concepts/author-epic-split-subflow.md)
- detail: [epic split result](epic-split-result.md)
- tests: `workflows/tests/author/epic_split/test_flow.py::test_creates_only_ordered_epic_skeletons_after_review_rework`

## Fields

### roadmap
- type: `str`
- required: true
- semantics: path to the approved roadmap document that owns the milestone and defines its scope
- verify: json_path(path="$.roadmap", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args`
- detail: [epic split prompt args](concepts/epic-split-prompt-args.md)

### milestone
- type: `str`
- required: true
- semantics: path to the milestone document inside the roadmap, containing the `epics:` list to be replaced
- verify: json_path(path="$.milestone", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args`
- detail: [epic split prompt args](concepts/epic-split-prompt-args.md)

### epics_dir
- type: `str`
- required: true
- semantics: canonical directory path where new epic skeleton documents are created
- verify: json_path(path="$.epics_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args`
- detail: [epic split prompt args](concepts/epic-split-prompt-args.md)

### review_notes
- type: `str`
- default: empty string on initial split, populated with review findings on rework
- required: false
- semantics: feedback from the review turn applied to the split, empty on the first invocation
- verify: json_path(path="$.review_notes", equals="")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args`
- detail: [epic split prompt args](concepts/epic-split-prompt-args.md)

## Response

### status
- type: literal `complete` or `blocked`
- required: true
- semantics: whether the agent created the ordered skeleton list or encountered a blocking product decision
- verify: json_path(path="$.status", matches="^(complete|blocked)$")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitResult`
- detail: [epic split result](epic-split-result.md)

### notes
- type: `str`
- required: true
- semantics: description of the ordered skeleton list and its rationale, or the blocking question
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitResult`
- detail: [epic split result](epic-split-result.md)

