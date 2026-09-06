---
type: format
slug: author-write-epic-prompt
title: Author write-epic prompt
---
# Author write-epic prompt

The epic-author flow renders this template for its high-power authoring turn. It directs the
  agent to research one approved roadmap segment, write the complete epic narrative, and record
  researched durable seeds without creating stories or changing the feature book. The expected
  response is a JSON object with `status` set to `complete` or `blocked` and a one-line `notes`
  value.

- file: `workflows/src/workhorse_workflows/author/epic_author/prompts/write-epic.md`
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.author_epic`
- detail: [author epic-author subflow](concepts/author-epic-author-subflow.md)
- tests: `workflows/tests/author/epic_author/test_flow.py::_Agent.__call__`

## Fields

### epic
- type: `str`
- required: true
- semantics: the one explicit epic whose narrative and seeds the agent must author
- verify: json_path(path="$.epic", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.author_epic`

### epic_dir
- type: `str`
- required: true
- semantics: the canonical epic directory containing the document to author
- verify: json_path(path="$.epic_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.author_epic`

### roadmap
- type: `str`
- required: true
- semantics: the approved roadmap document that supplies the epic's scope and decisions
- verify: json_path(path="$.roadmap", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.author_epic`

### features_dir
- type: `str`
- required: true
- semantics: the read-only OKF feature-book directory available as discovery context
- verify: json_path(path="$.features_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.author_epic`

### status
- type: `str`
- required: true
- semantics: whether the authoring turn completed or is blocked
- verify: json_path(path="$.status", matches="^(complete|blocked)$")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.author_epic`

### notes
- type: `str`
- required: true
- semantics: the completion note or blocking question returned with the turn
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.author_epic`
