---
type: concept
slug: coverage-defect-result-fields
title: Coverage defect result fields
---
# Coverage defect result fields

`Defects` is the shared result shape for `validate_story`, `check_story_grounding`,
`validate_coverage`, and `validate_artifacts`. Its two fields are a paired report rather than
alternative representations: `ok` decides whether a validator found a defect, and `errors`
provides the operator- and agent-facing findings when one exists, one per line.

The schema does not rank either field or permit one to substitute for the other. Consumers first
use `ok` to decide whether the validator holds, then use `errors` to explain a failing result.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Defects`
- rule: use `ok` for the validator verdict and `errors` for one-per-line diagnostic findings; neither field is an alternative to the other
