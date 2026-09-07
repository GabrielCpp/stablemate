---
type: format
slug: hello-world-greeting
title: Hello-world greeting
---
# Hello-world greeting

The [hello-world workflow composition root](concepts/hello-world-workflow-composition-root.md)
accepts this typed response only after the greeting prompt's JSON reply validates, then returns it
as the workflow result.

- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::Greeting`
- tests: `workflows/tests/test_hello_world.py::test_a_real_turn_reaches_done_with_the_agents_own_greeting`

## Fields

### greeting

- type: `str`
- default: none
- verify: json_path(path="$.greeting", equals="Hello, globex.")
- required: true because the agent reply must provide a greeting
- verify: json_path(path="$.greeting", equals="Hello, globex.")
- semantics: the validated friendly sentence returned by the agent turn
- verify: json_path(path="$.greeting", equals="Hello, globex.")
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::Greeting`
