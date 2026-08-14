---
type: concept
slug: get-backend
title: get_backend — select a harness backend by name
---
# get_backend

The runtime selector for the [`AgentBackend`](agent-backend.md) `extends:` fan: resolves a name to
a concrete, cached backend instance. Driven by [`workhorse-<name> run`](../workhorse.md#run)'s `--cli`
flag, which [validates the name eagerly](../workhorse.md#run) at startup so an unknown one fails
before a run directory exists rather than at the first agent turn.

It lives in `runner/backends/registry.py` — **deliberately not `__init__.py`**. A registry has to
import every adapter to map a name to a class, so putting it beside the port would make
`from workhorse.runner.backends import AgentBackend` drag in all five CLIs. Keeping the two apart
means importing the type costs one small module, and only code that actually *selects* a backend
pays for the adapters.

- code: `workhorse/workhorse/runner/backends/registry.py::get_backend`
- verify: `workhorse/tests/test_backends.py::test_default_backend_is_claude_when_nothing_names_one`,
  `workhorse/tests/test_backends.py::test_config_default_cli_selects_backend`,
  `workhorse/tests/test_backends.py::test_env_var_beats_config_default_cli`,
  `workhorse/tests/test_backends.py::test_unknown_config_default_cli_fails_like_any_typo`,
  `workhorse/tests/test_backends.py::test_env_var_selects_backend`,
  `workhorse/tests/test_backends.py::test_explicit_name_overrides_env`,
  `workhorse/tests/test_backends.py::test_unknown_backend_raises`,
  `workhorse/tests/test_backends.py::test_get_backend_caches_instance`,
  `workhorse/tests/test_backends.py::test_non_claude_backends_registered`

## Contract

- **Input:** `name: str | None = None`.
- **Resolution order:** explicit `name` → the `AGENT_CLI` environment variable → the shared
  config's `default_cli` key ([resolve_default_cli](config.md#resolve_default_cli)) →
  `"claude"`. The chosen value is `.strip().lower()`-ed, so `AGENT_CLI=" Codex "` resolves.
- **Where a configured name is checked:** here. `stablemate_core` stores `default_cli` without
  validating it — the registry of real names is this module's — so a misspelled config value raises
  the same `ValueError` a typo'd `--cli` does, and the message names `default_cli` alongside
  `AGENT_CLI` so the operator looks in the right place.
- **Output:** the [`AgentBackend`](agent-backend.md) subclass instance registered under that key.
  Backends are stateless by contract, so **one instance per name is cached and reused** for the
  process's lifetime — `get_backend("claude") is get_backend("claude")`.
- **Raises:** `ValueError` on an unknown name, naming the value and listing the available keys in
  sorted order. Fail fast: a typo'd `--cli` is a configuration error, not something to fall back to
  the default for.

## The registry

`_REGISTRY` maps five names to their classes, one import per adapter module:

| Name | Class | Page |
| --- | --- | --- |
| `claude` | `ClaudeBackend` | [claude-backend](claude-backend.md) |
| `codex` | `CodexBackend` | [codex-backend](codex-backend.md) |
| `copilot` | `CopilotBackend` | [copilot-backend](copilot-backend.md) |
| `cline` | `ClineBackend` | [cline-backend](cline-backend.md) |
| `opencode` | `OpenCodeBackend` | [opencode-backend](opencode-backend.md) |

Adding a CLI is therefore two edits and no engine change: a new module implementing the
[port](agent-backend.md#contract), and one row here.

`_CACHE` holds the instantiated backends. It is keyed by the *resolved* name, so the env-var path
and the explicit-name path share an entry.

## Related pieces

- [`AgentBackend`](agent-backend.md) — the port every registered class implements; declared in
  `backends/__init__.py`, which this module is deliberately kept out of.
- [`AgentRunner.run`](run-agent.md) — the consumer: the runner is constructed with the resolved
  backend once per run and drives it every agent turn without re-resolving.
- [`workhorse-<name> run`](../workhorse.md#run) — where `--cli` arrives, and where an unknown name is
  turned into a stderr message and exit `1`.
