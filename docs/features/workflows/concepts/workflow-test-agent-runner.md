---
type: concept
slug: workflow-test-agent-runner
title: Workflow test agent runner
---
# Workflow test agent runner

`StubRunner` is the test-only `AgentRunner` substitute used when a workflow drive needs a
scripted agent reply. It preserves the production runner type and forwards each turn's complete
argument set to the supplied callable, so prompt rendering, reply validation, turn recording,
and flow transitions remain on the production path while no agent CLI or backend is resolved.

- code: `workflows/tests/_fakes.py::StubRunner`
- tests: `workflows/tests/test_hello_world.py::test_a_real_turn_reaches_done_with_the_agents_own_greeting`

## Methods

### __init__

Creates the runner with a null backend and retains the scripted agent callable.

- sig: `StubRunner.__init__(self, agent: Any) -> None`
- does: configures the inherited runner with a backend that selects no agent CLI
- verify: absent(subject="agent CLI resolution")
- does: retains the supplied callable as the scripted agent
- verify: json_path(path="$.greeting", equals="Hello, globex.")
- code: `workflows/tests/_fakes.py::StubRunner.__init__`
- tests: `workflows/tests/test_hello_world.py::test_a_real_turn_reaches_done_with_the_agents_own_greeting`

### run

Delegates an engine turn unchanged to the scripted agent callable. The `agent` callable the
hello-world test passes into `StubRunner` is the canonical scripted shape — it records the
context at the call site and returns the `(rendered_prompt, raw_reply)` tuple the engine
expects.

- sig: `StubRunner.run(self, *args: Any, **kwargs: Any) -> tuple[str, dict[str, Any]]`
- does: forwards all positional and keyword arguments to the scripted agent
- verify: json_path(path="$.greeting", equals="Hello, globex.")
- returns: the scripted agent's rendered prompt and raw reply
- verify: json_path(path="$.greeting", equals="Hello, globex.")
- code: `workflows/tests/_fakes.py::StubRunner.run`
- code: `workflows/tests/test_hello_world.py::test_a_real_turn_reaches_done_with_the_agents_own_greeting.agent`
- tests: `workflows/tests/test_hello_world.py::test_a_real_turn_reaches_done_with_the_agents_own_greeting`
