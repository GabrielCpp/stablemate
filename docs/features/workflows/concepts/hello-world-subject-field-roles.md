---
type: concept
slug: hello-world-subject-field-roles
title: Hello-world subject field roles
---
# Hello-world subject field roles

`Subject` carries the requested subject and a measurement of that same subject. The
`measure` node receives `name`, returns it unchanged, and computes `letters` as its
length. The workflow passes `letters` into the greeting turn while retaining `name` as
the subject used to request the greeting.

Neither field replaces the other: use `name` when the requested subject is needed and
use `letters` when its character count is needed.

- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::Subject`
- rule: use `name` for the requested subject and `letters` for its character count; neither field is a replacement for the other
