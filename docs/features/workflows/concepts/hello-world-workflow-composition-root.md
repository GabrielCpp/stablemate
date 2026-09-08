---
type: concept
slug: hello-world-workflow-composition-root
title: Hello-world workflow composition root
---
# Hello-world workflow composition root

The `workhorse-hello-world` console script imports `main`, which binds a registry to the
two-state `HelloWorld` machine. The machine first produces a
[subject](../hello-world-subject.md), then gives its name and measured letter count to the
[greeting prompt](../hello-world-greeting-prompt.md); the agent reply is validated as a
[greeting](../hello-world-greeting.md) before the run finishes. Its
[package initializer](hello-world-workflow-package-initializer.md) exposes no separate API.

The registry includes the `hello-world` blueprint and supplies a deterministic greeting for
`--dry-run`, allowing the complete machine to run without an agent CLI.

- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::blueprint`
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::workflow`
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::main`
- tests: `workflows/tests/test_hello_world.py::test_the_documented_command_is_declared`
- tests: `workflows/tests/test_hello_world.py::test_the_documented_dry_run_walks_the_machine_green`
- tests: `workflows/tests/test_hello_world.py::test_a_real_turn_reaches_done_with_the_agents_own_greeting`
- detail: [Workflow kit tools](workflow-kit-tools.md)
- detail: [Workflow kit git](workflow-kit-git.md)
- detail: [Hello-world main concept selection](hello-world-main-concept-selection.md)
- detail: [Hello-world main contexts](hello-world-main-contexts.md)

## Methods

### measure

Measures the configured subject before the agent turn.

- sig: `measure(logger: Logger, name: str) -> Subject`
- does: logs that the supplied name is being measured
- does: creates a Subject carrying the supplied name
- does: calculates the Subject letter count from the supplied name
- returns: a Subject with its name and calculated letter count
- verify: json_path(path="$.name", equals="globex")
- verify: json_path(path="$.letters", equals=6)
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::measure`
- tests: `workflows/tests/test_hello_world.py::test_a_real_turn_reaches_done_with_the_agents_own_greeting`

### start

Starts the workflow's deterministic state before its agent turn.

- sig: `HelloWorld.start(self) -> Continue`
- does: calls measure with the configured workflow name
- does: carries the measured Subject into the transition to greet
- does: stores the measured letter count in the transition under `letters`
- returns: a Continue transition targeting greet
- verify: json_path(path="$.letters", equals=6)
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::HelloWorld.start`
- tests: `workflows/tests/test_hello_world.py::test_a_real_turn_reaches_done_with_the_agents_own_greeting`

### greet

Runs the only agent turn and completes the workflow with its typed reply.

- sig: `HelloWorld.greet(self, letters: int) -> Done`
- does: renders the greeting prompt with the workflow name and transitioned letter count
- does: validates the agent reply as a Greeting before using it
- does: logs the validated greeting text
- returns: a Done result carrying the validated Greeting
- verify: json_path(path="$.greeting", equals="Hello, globex.")
- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::HelloWorld.greet`
- tests: `workflows/tests/test_hello_world.py::test_a_real_turn_reaches_done_with_the_agents_own_greeting`
