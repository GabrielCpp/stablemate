---
type: concept
slug: get-backend
title: get_backend — select a harness backend by name
---
# get_backend

The runtime selector for the [AgentBackend](agent-backend.md) `extends:` fan: resolves a name to a
concrete, cached backend instance. Driven by [workhorse run](../workhorse.md#run)'s `--cli` flag.

- code: `workhorse/workhorse/runner/backends.py::get_backend`

## Contract

- **Input:** `name: str | None`.
- **Resolution order:** explicit `name` → `AGENT_CLI` env var → `"claude"`. The result is
  lowercased and stripped.
- **Output:** the [AgentBackend](agent-backend.md) registered under that key. Backends are
  stateless, so one instance per name is cached and reused.
- **Raises:** `ValueError` (fail fast) on an unknown name, listing the available keys.
