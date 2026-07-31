---
type: concept
slug: claude-backend
title: ClaudeBackend — the claude harness
---
# ClaudeBackend — the claude harness

The [AgentBackend](agent-backend.md) implementation for the Claude Code CLI (`claude -p`) — the
default backend, selected when [run](../workhorse.md#run)'s `--cli` (via
[get_backend](get-backend.md)) resolves to `claude` or is left unset. It is the odd one out twice
over: the only backend that **compacts in place** (`supports_compaction = True`), and the only one
whose stream is read by a fused loop-plus-vocabulary function
([`_stream_events`](stream-events.md)) rather than by the generic
[`stream_jsonl`](stream-jsonl.md) plus a small adapter.

Unlike every other adapter, this module **owns** its protocol code rather than adapting a shared
implementation. That is the inversion loop 2 landed. Claude's `stream-json` / `--resume` /
`/compact` handling used to live in the CLI-agnostic recovery ladder, with the backend facade
delegating back into it — which made the generic ring the home of one implementation and forced
the ladder and `backends` to import each other lazily. Claude is now a sibling of every other
adapter in its own `runner/backends/claude.py`, and the ladder imports it not at all; the lazy
imports and the cycle they worked around are both gone.

- code: `workhorse/workhorse/runner/backends/claude.py::ClaudeBackend`
- extends: [AgentBackend](agent-backend.md)
- verify: `workhorse/tests/test_backends.py::test_default_backend_is_claude`,
  `workhorse/tests/test_backends.py::test_claude_effort_maps_to_native_flag`,
  `workhorse/tests/test_backends.py::test_claude_no_effort_omits_flag`,
  `workhorse/tests/test_config_harness_env.py::test_compaction_runs_under_the_same_env`

## Contract

- `name` = `"claude"`.
- `default_model` = `"sonnet"` — the only backend with a usable built-in default; every other
  backend leaves `default_model` unset (`None`) and needs a node/config `model` entry.
- `supports_compaction` = `True` — and it is the only implementation for which
  [Layer 2 of the ladder](run-agent.md#the-ladder) does anything at all.
- **`run_turn(prompt, node_id, session_id_path, model=None, *, timeout, resilience, cwd=None,
  add_dirs=None, effort=None)`** — `timeout` and `resilience` are keyword-only and **required**
  ([why](agent-backend.md#run_turn-abstract)); neither carries a default here, so no caller can
  silently run a turn under the engine's assumptions instead of the run's. Delegates to the
  module-level [`_run_cli`](run-claude-cli.md), forwarding every argument unchanged plus
  `env_extra=self.harness_env()`. Claude has a native reasoning-effort flag
  (`--effort low|medium|high|xhigh|max`), so `effort` passes straight through rather than being
  translated or clamped — contrast [CodexBackend](codex-backend.md) and
  [`_aider_effort`](aider-backend.md#_aider_effort), which clamp `xhigh`/`max` down to `high`.
  Raises the `BackendInvocationError` [`classify_turn`](classify-turn.md#ladder-first-match-wins)
  raises inside `_run_cli`.
- **`compact(session_id_path, node_id, model=None, *, timeout, resilience)`** — delegates to
  [`_compact_session`](compact-session.md), forwarding `resilience` and `timeout` (the same
  keyword-only pair, for the same reason) **and** `env_extra=self.harness_env()`. That last one is
  not incidental: a knob that shapes a turn must also shape the `/compact` turn, or compaction runs
  under a different CLI configuration than the conversation it is compacting
  (`test_compaction_runs_under_the_same_env`). Never raises — see that page's contract.

`harness_env()` is [the port's concrete method](agent-backend.md#harness_env-concrete), resolving
`[harness.claude].env` from the operator's config **per turn** rather than once at import, so a
config edit lands on the next turn of a running workflow.

## The protocol this module owns

Five symbols, none of which any other backend touches:

| Symbol | Role |
|---|---|
| [`_run_cli`](run-claude-cli.md) | builds one turn's argv, resumes a session, classifies the result |
| [`_compact_session`](compact-session.md) | the `/compact` turn behind `compact` |
| [`ClaudeTurnStream`](stream-events.md#claudeturnstream) | what one turn yielded, as its stream went past |
| [`_stream_events`](stream-events.md) | parses `--output-format stream-json` into that struct |
| [`_emit_event`](emit-event.md) / [`_tool_summary`](tool-summary.md) | the live-progress echo |

`_run_cli` and `_compact_session` are **module-level functions, not methods**, and the class calls
them by local name. There is no indirection left to preserve here: importing *the module* rather
than its names — so a monkeypatched function resolved at call time, and so no import cycle formed
— was a property of the era when the implementation lived in the ladder. Both reasons died with
the split, and `claude.py` now imports [`AgentBackend`](agent-backend.md) at module scope like any
other adapter.

## Related pieces

- [`AgentBackend`](agent-backend.md) — the port this implements, and the only thing the ladder
  knows about it.
- [`_run_cli`](run-claude-cli.md) — the turn runner `run_turn` is a single delegation to: builds
  the `claude --dangerously-skip-permissions --output-format stream-json --verbose
  [--model][--effort][--add-dir ...] -p [--resume <sid>]` argv, streams it, classifies it.
- [`_compact_session`](compact-session.md) — the in-place compaction `compact` delegates to; the
  only implementation of [Layer 2](run-agent.md#the-ladder) in the tree.
- [`AgentRunner.turn`](agent-turn.md) — layer 1 of [the resilience ladder](run-agent.md#the-ladder)
  and the caller of `run_turn` for every backend, Claude included.
- [`get_backend`](get-backend.md) — resolves `"claude"` (or no `--cli`/`AGENT_CLI` at all) to a
  cached `ClaudeBackend()` instance.
- [CodexBackend](codex-backend.md) / [CopilotBackend](copilot-backend.md) /
  [OpenCodeBackend](opencode-backend.md) / [AiderBackend](aider-backend.md) — the four sibling
  adapters, each in its own module under `runner/backends/`, each sharing a generic stream loop,
  and none of which can compact.
