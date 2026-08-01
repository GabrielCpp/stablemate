---
type: concept
slug: agent-backend
title: AgentBackend — the harness backend port
---
# AgentBackend

The port every agent harness implements: one agent CLI behind a uniform interface, **stateless** —
safe to share, which is why [`get_backend`](get-backend.md) caches one instance per name.
[`AgentRunner.run`](run-agent.md) drives whichever concrete backend the run resolved, once per
agent turn, and never learns which CLI it got.

`runner/backends/__init__.py` declares the port **and nothing else**. Each CLI owns its protocol in
its own sibling module — [`claude`](claude-backend.md), [`codex`](codex-backend.md),
[`copilot`](copilot-backend.md), [`opencode`](opencode-backend.md), [`aider`](aider-backend.md) —
and [`registry`](get-backend.md), the only module that imports all of them, maps a name to a class.
Importing the port therefore drags in no adapter: a module that only needs the type for an
annotation pays for one small file.

It is an **ABC, not a `Protocol`**: a backend is a plugin point with real shared behavior
(`harness_env` below has an implementation every subclass inherits), and an unimplemented abstract
method should fail loudly at construction rather than silently satisfy a structural check.

- code: `workhorse/workhorse/runner/backends/__init__.py::AgentBackend`
- verify: `workhorse/tests/test_backends.py::test_non_claude_backends_registered`,
  `workhorse/tests/test_config_harness_env.py::test_every_backend_forwards_its_own_table`

## Contract

### Class attributes

Declared with defaults on the base; a subclass overrides what differs.

| Attribute | Default | Meaning |
| --- | --- | --- |
| `name: str` | `"agent"` | the registry key (e.g. `"codex"`), used in log lines, error messages, and `[harness.<name>]` config lookup |
| `default_model: str \| None` | `None` | the model to use when neither the node nor the run names one; `None` means "let the CLI pick its own default" |
| `supports_compaction: bool` | `False` | whether `compact` can actually do anything, so the [ladder](run-agent.md) can skip Layer 2 rather than call and discard |

### `run_turn` (abstract)

```python
def run_turn(
    self, prompt: str, node_id: str, session_id_path: Path | None,
    model: str | None = None, *, timeout: float, resilience: AgentResilience,
    cwd: str | None = None, add_dirs: list[str] | None = None,
    effort: str | None = None,
) -> str
```

Run one non-interactive turn for `prompt` and return the final result text.

- `node_id` — the workflow node this turn belongs to; used for log-line prefixes and carried into
  every raised error so a failure names the node it came from.
- `session_id_path` — where to persist the CLI's session id so the next turn on this node resumes
  ([`read_session_id`](read-session-id.md) reads it back); `None` when the caller wants no session
  continuity.
- `timeout` and `resilience` are **keyword-only and required**. Nothing here reads an env var or a
  module constant for a timing bound: the run's [`AgentResilience`](config.md) is threaded in by
  the caller, so a test can shorten every wait by passing a different value.
- `cwd` sets the subprocess working directory, which is what governs the CLI's own
  project-instruction and skill discovery; `add_dirs` are extra directories granted to the harness;
  `effort` (`low`/`medium`/`high`) each backend translates into its own knob, or ignores.

**Raises** [`BackendInvocationError`](classify-turn.md#backendinvocationerror) on failure, with the
`transient` / `context_overflow` / `cap` flags set by
[`classify_turn`](classify-turn.md#ladder-first-match-wins), so
[`AgentRunner.run`](run-agent.md)'s ladder can tell recoverable from terminal without parsing a
message.

### `compact` (abstract)

```python
def compact(
    self, session_id_path: Path | None, node_id: str, model: str | None = None,
    *, timeout: float, resilience: AgentResilience,
) -> bool
```

Best-effort: compact the node's session in place to free context so the same prompt can be retried,
and return whether it helped. A backend whose CLI has no in-place compaction returns `False`
(and declares `supports_compaction = False`), and the ladder falls through to
[reframe](rephrase-prompt.md) instead. Only [`ClaudeBackend`](claude-backend.md) implements it
substantively, via [`_compact_session`](compact-session.md).

### `harness_env` (concrete)

```python
def harness_env(self) -> dict[str, str]:
    return resolve_harness_env(self.name)
```

The one piece of shared behavior on the port: the operator-configured `[harness.<name>].env` table
from [config](config.md), returned as the extra environment to layer over the inherited one when
spawning this CLI. Each backend passes it into its own spawn as `env_extra` (see
[`stream_jsonl`](stream-jsonl.md#contract) and
[`stream_subprocess`](stream-subprocess.md#contract)).

It is a method read **per turn**, not a value captured at startup — a long-running run picks up an
edited config on its next turn, and a test can point one backend at a different API base without
rebuilding the runner.

## Implementations

Five, each in its own module, each overriding `name` plus `run_turn`/`compact`:

- [`ClaudeBackend`](claude-backend.md) — the default; the only one with real compaction.
- [`CodexBackend`](codex-backend.md), [`CopilotBackend`](copilot-backend.md),
  [`OpenCodeBackend`](opencode-backend.md) — the JSONL-streaming three, sharing
  [`stream_jsonl`](stream-jsonl.md) and [`finalize_turn`](finalize-turn.md).
- [`AiderBackend`](aider-backend.md) — plain text output, via
  [`_run_text_turn`](run-text-turn.md).

Selected at runtime by [`get_backend`](get-backend.md), which
[`workhorse-<name> run`](../workhorse.md#run)'s `--cli` flag and the `AGENT_CLI` env var drive.
