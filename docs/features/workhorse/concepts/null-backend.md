---
type: concept
slug: null-backend
title: NullBackend — absent agent adapter
---
# NullBackend — absent agent adapter

The null object used when a run has no selected agent CLI. It keeps the runner's backend field
non-nullable, but is deliberately not registered as a selectable CLI. A turn reaching an agent node
fails immediately with an actionable non-recoverable error rather than fabricating outputs through
the recovery ladder.

- code: `workhorse/workhorse/runner/backends/null.py::NullBackend`
- extends: [AgentBackend](agent-backend.md)
- tests: `workhorse/tests/test_backends.py::test_null_backend_is_not_selectable`,
  `workhorse/tests/test_backends.py::test_run_config_without_a_cli_holds_the_null_backend`,
  `workhorse/tests/test_backends.py::test_agentless_run_fails_its_first_agent_node_with_a_sentence`
- detail: [Agent backend selection](agent-backend-selection.md)

## Fields

### name
- type: `str`
- default: `"none"`
- required: false
- semantics: identifies the absent-CLI adapter in errors
- verify: json_path(path="$.name", equals="none")
- semantics: is not a backend registry key
- verify: absent(subject="NullBackend in the backend registry")
- code: `workhorse/workhorse/runner/backends/null.py::NullBackend`
- detail: [NullBackend selection](null-backend-selection.md)

### default_model
- type: `str | None`
- default: `None`
- required: false
- semantics: no model exists when no CLI is configured
- verify: json_path(path="$.default_model", absent=true)
- code: `workhorse/workhorse/runner/backends/null.py::NullBackend`
- detail: [NullBackend selection](null-backend-selection.md)

### supports_compaction
- type: `bool`
- default: `False`
- required: false
- semantics: the absent adapter cannot compact a session
- verify: json_path(path="$.supports_compaction", equals=false)
- code: `workhorse/workhorse/runner/backends/null.py::NullBackend`
- detail: [NullBackend selection](null-backend-selection.md)

## Methods

### run_turn
- sig: `run_turn(prompt: str, node_id: str, session_id_path: Path | None, model: str | None = None, *, prompt_path: Path | None = None, timeout: float, resilience: AgentResilience, cwd: str | None = None, add_dirs: list[str] | None = None, effort: str | None = None) -> str`
- does: refuses an agent turn because no CLI was selected
- raises: `BackendInvocationError` naming the node and instructing the operator to pass `--cli` or set `AGENT_CLI`
- verify: absent(subject="agent turn result from a run with no CLI")
- code: `workhorse/workhorse/runner/backends/null.py::NullBackend.run_turn`

### compact
- sig: `compact(session_id_path: Path | None, node_id: str, model: str | None = None, *, timeout: float, resilience: AgentResilience) -> bool`
- does: declines compaction because there is no session
- returns: `false`
- verify: json_path(path="$.compacted", equals=false)
- code: `workhorse/workhorse/runner/backends/null.py::NullBackend.compact`
