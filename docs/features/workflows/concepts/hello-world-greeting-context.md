---
type: concept
slug: hello-world-greeting-context
title: Hello-world Greeting Context
---
# Hello-world Greeting Context

[`Greeting`](../../../../workflows/src/workhorse_workflows/hello_world/workflow.py) is the one-field
response model declared at `workflow.py::Greeting`. `HelloWorld.greet` passes it as the agent
turn's `returns=` contract and returns the validated instance in `Done(reply)`.

Use the [greeting prompt field](../hello-world-greeting-prompt.md#greeting) to specify the JSON
value the agent must supply. Use the [workflow greeting field](../hello-world-greeting.md#greeting)
to specify that same validated value as the workflow result. Neither representation supersedes the
other: each documents its boundary of the same `Greeting` model.

- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::Greeting`
- rule: choose the prompt field for the agent reply contract and the workflow field for the validated workflow result; neither is preferred
- tests: `workflows/tests/test_hello_world.py::test_a_real_turn_reaches_done_with_the_agents_own_greeting`
