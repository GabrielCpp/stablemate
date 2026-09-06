---
type: format
slug: hello-world-greeting-prompt
title: Hello-world greeting prompt
---
# Hello-world greeting prompt

The [hello-world workflow composition root](concepts/hello-world-workflow-composition-root.md)
renders this template for its only agent turn. It receives the measured subject data and demands
JSON matching the [greeting](hello-world-greeting.md) shape without reading or writing files.

- file: `workflows/src/workhorse_workflows/hello_world/prompts/greet.md`
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::HelloWorld.greet`
- tests: `workflows/tests/test_hello_world.py::test_a_real_turn_reaches_done_with_the_agents_own_greeting`

## Fields

### name

- type: `str`
- default: none; the workflow always renders a configured name
- verify: json_path(path="$.name", equals="globex")
- required: true
- verify: json_path(path="$.name", equals="globex")
- semantics: the name the agent must greet
- verify: json_path(path="$.name", equals="globex")
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::HelloWorld.greet`

### letters

- type: `int`
- default: none; the workflow always renders its measured count
- verify: json_path(path="$.letters", equals=6)
- required: true
- verify: json_path(path="$.letters", equals=6)
- semantics: the name character count the agent must mention
- verify: json_path(path="$.letters", equals=6)
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::HelloWorld.greet`

### greeting

- type: `str`
- default: none; the agent must return the JSON key
- verify: json_path(path="$.greeting", equals="Hello, globex.")
- required: true
- verify: json_path(path="$.greeting", equals="Hello, globex.")
- semantics: the one-sentence friendly greeting output after JSON validation
- verify: json_path(path="$.greeting", equals="Hello, globex.")
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::Greeting`
