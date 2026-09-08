---
type: concept
slug: hello-world-greeting-prompt-input-fields
title: Hello-world Greeting Prompt Input Fields
---
# Hello-world Greeting Prompt Input Fields

`HelloWorld.greet` renders the greeting prompt with both the configured workflow name and the
measured character count. The [name](../hello-world-greeting-prompt.md#name) field identifies
the greeting recipient; the [letters](../hello-world-greeting-prompt.md#letters) field gives the
count the agent must mention. They are complementary inputs to one agent turn, not alternative
implementations.

Neither field ranks above the other: a valid prompt needs the name to address and the count to
report. The method supplies each in its own argument, and the source records no legacy path,
deprecation, or preferred substitute.

- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::HelloWorld.greet`
- rule: use `name` for the greeting recipient and `letters` for its measured character count; neither field is preferred or deprecated
