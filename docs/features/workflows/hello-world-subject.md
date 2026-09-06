---
type: format
slug: hello-world-subject
title: Hello-world subject
---
# Hello-world subject

The [hello-world workflow composition root](concepts/hello-world-workflow-composition-root.md)
returns this typed value from its measuring node and carries its letter count into the next state.

- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::Subject`
- tests: `workflows/tests/test_hello_world.py::test_a_real_turn_reaches_done_with_the_agents_own_greeting`

## Fields

### name

- type: `str`
- default: none; the caller must supply a name
- verify: json_path(path="$.name", equals="globex")
- required: true
- verify: json_path(path="$.name", equals="globex")
- semantics: the workflow subject whose greeting is requested
- verify: json_path(path="$.name", equals="globex")
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::Subject`

### letters

- type: `int`
- default: none; measurement always supplies the value
- verify: json_path(path="$.letters", equals=6)
- required: true
- verify: json_path(path="$.letters", equals=6)
- semantics: the number of characters in name
- verify: json_path(path="$.letters", equals=6)
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::Subject`
