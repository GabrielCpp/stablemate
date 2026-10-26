---
type: format
slug: unit-assessment
title: Survey unit assessment reply
---
# Survey unit assessment reply

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitAssessment` @59f51b5b79f1
- detail: [author surveyor subflow](../concepts/author-surveyor-subflow.md)

The assessor's response for one unit. `split` requests subdivision; the other statuses are
assessable outcomes.

## Fields

### status
- type: string
- default: empty string
- required: false
- semantics: assessment outcome: `assessed`, `clean`, `blocked`, or `split`
- verify: json_path(path="$.status", equals="example status")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitAssessment` @59f51b5b79f1
- detail: [unit assessment reply fields](../concepts/unit-assessment-reply-fields.md)

### notes
- type: string
- default: empty string
- required: false
- semantics: assessment explanation or split/blocked context
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitAssessment` @59f51b5b79f1
- detail: [unit assessment reply fields](../concepts/unit-assessment-reply-fields.md)
