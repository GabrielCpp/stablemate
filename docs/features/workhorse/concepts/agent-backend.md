---
type: concept
slug: agent-backend
title: AgentBackend — the harness backend abstraction
---
# AgentBackend

The abstract base every agent harness implements: one agent CLI behind a uniform interface,
**stateless** (safe to share/cache one instance). [get_backend](get-backend.md) returns the
concrete one whose registry key matches [workhorse run](../workhorse.md#run)'s `--cli` value; the
[workflow](workflow.md) execution loop calls it per `agent` node. Implementations extend it —
[claude](claude-backend.md) (default), [codex](codex-backend.md), [copilot](copilot-backend.md),
[aider](aider-backend.md), [opencode](opencode-backend.md).

- code: `workhorse/workhorse/runner/backends.py::AgentBackend`

## Contract

- `name: str` — the registry key (e.g. `claude`), used in logs and `AGENT_CLI` matching.
- **`run_turn(prompt, session_id_path, model=None, add_dirs=(), cwd=None, effort=None) -> str`**
  (abstract) — run one non-interactive turn for `prompt`; return the final result text. Persist
  the session id to `session_id_path` when the CLI supports resume. `cwd` sets the subprocess
  working directory (controls CLAUDE.md/skills discovery); `add_dirs` are extra granted dirs;
  `effort` (`low`/`medium`/`high`) each backend translates to its own knob. **Raises**
  `agent.BackendInvocationError` on failure (empty/absent result) so the caller's resilience
  ladder can catch it.
- **`compact(session_id_path, model=None) -> bool`** (abstract) — best-effort: compact the node's
  session to free context so the same prompt can be retried; return whether it helped. Backends
  without in-place compaction return `False`, and the caller falls back to reframe.

## Implementations

Each `extends:` this base and overrides `name` + `run_turn`/`compact`: [claude](claude-backend.md)
(default — a thin adapter over `runner/agent.py`'s Claude functions), [codex](codex-backend.md),
[copilot](copilot-backend.md), [aider](aider-backend.md), [opencode](opencode-backend.md).
Selected at runtime by [get_backend](get-backend.md), which the `--cli` flag on
[run](../workhorse.md#run) drives.
