---
type: format
slug: author-resolve-operator-prompt
title: Author resolve-operator prompt
---
# Author resolve-operator prompt

The author flows render this shared diagnostic template after a blocked writing or validation
result. The epic-author flow supplies `block_stage: "write-epic"`; the story-author flow supplies
`block_stage: "write-story"`. It asks the agent to investigate and brief the operator without
making the product or scope decision. The expected response is an escalated JSON decision with
one-line notes and concrete investigated items.

- file: `workflows/src/workhorse_workflows/author/shared/prompts/resolve-operator.md`
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.resolve_epic`
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._resolve`
- detail: [author epic-author subflow](concepts/author-epic-author-subflow.md)
- detail: [author story-author prompt contracts](concepts/author-story-author-prompt-contracts.md)
- tests: `workflows/tests/author/epic_author/test_flow.py::_Agent.__call__`

## Fields

### context_path
- type: `str`
- required: true
- semantics: the operator context file the diagnostic brief must preserve and append to
- verify: json_path(path="$.context_path", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.resolve_epic`
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._resolve`

### epic_dir
- type: `str`
- required: true
- semantics: the canonical epic directory whose documents and scope the diagnostic turn investigates
- verify: json_path(path="$.epic_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.resolve_epic`
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._resolve`

### block_stage
- type: `str`
- required: true
- semantics: the authoring stage identifier supplied to the diagnostic turn, such as `write-epic` or `write-story`
- verify: json_path(path="$.block_stage", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.resolve_epic`
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._resolve`

### block_notes
- type: `str`
- required: true
- semantics: the blocked result or validation errors that define the question for investigation
- verify: json_path(path="$.block_notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.resolve_epic`
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._resolve`

### decision
- type: `str`
- required: true
- semantics: the diagnostic outcome, which must be `escalated` for this resolver
- verify: json_path(path="$.decision", equals="escalated")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.resolve_epic`
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._resolve`

### notes
- type: `str`
- required: true
- semantics: the one-line plain-language statement of what remains blocked
- verify: json_path(path="$.notes", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.resolve_epic`
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._resolve`

### tried
- type: `list[str]`
- required: true
- semantics: concrete investigations and findings supplied to the operator
- verify: json_path(path="$.tried", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.resolve_epic`
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._resolve`
