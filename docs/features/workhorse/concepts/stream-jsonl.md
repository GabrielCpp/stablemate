---
type: concept
slug: stream-jsonl
title: stream_jsonl — the shared JSONL event loop
---
# stream_jsonl — the shared JSONL event loop

The generic newline-delimited-JSON turn runner shared by the three JSONL-speaking backends —
[`CodexBackend`](codex-backend.md), [`CopilotBackend`](copilot-backend.md),
[`OpenCodeBackend`](opencode-backend.md). Each backend builds its own `cmd` and supplies an
`on_event` callback that knows its CLI's own event vocabulary ([`_codex_on_event`](codex-on-event.md),
[`_copilot_on_event`](copilot-on-event.md), [`_opencode_on_event`](opencode-on-event.md));
`stream_jsonl` owns everything vocabulary-agnostic: spawning through
[`stream_subprocess`](stream-subprocess.md), per-line JSON parsing, non-JSON passthrough, and the
early-abort scan. A backend's `run_turn` calls it once, then hands the returned
[`TurnState`](finalize-turn.md#turnstate) to [`finalize_turn`](finalize-turn.md) to classify the
turn the same way every other backend does.

It is its own module, `runner/backends/jsonl.py`, so the shared loop is importable without dragging
in any CLI adapter.

- code: `workhorse/workhorse/runner/backends/jsonl.py::stream_jsonl`
- verify: `workhorse/tests/test_backends.py::test_opencode_cap_log_line_aborts_stream_early`,
  `workhorse/tests/test_backends.py::test_opencode_cap_structured_error_event_aborts_stream_early`,
  `workhorse/tests/test_backends.py::test_opencode_provider_header_timeout_aborts_into_short_retry`

## Contract

- **Input** — five positional, then keyword-only:
  - `cmd` — the argv to spawn, passed straight through to
    [`stream_subprocess`](stream-subprocess.md#contract).
  - `node_id` — the workflow node id; used only for log-line prefixes (`[{node_id}] ...`) and
    forwarded to `stream_subprocess`/`on_event`.
  - `timeout` — forwarded verbatim to `stream_subprocess`.
  - `stdin_data` — forwarded verbatim to `stream_subprocess` (a single-shot prompt on stdin, e.g.
    Codex's resume-with-prompt invocation; `None` for Copilot, which takes its prompt as a `-p`
    arg). Positional and required — a backend with nothing to write passes `None` explicitly.
  - `on_event` — an `(event: dict, state: TurnState, node_id: str) -> None` callback, invoked once
    per successfully parsed JSON object. **Three arguments, not four:** diagnostics are appended to
    `state.diagnostics` rather than to a separate list.
  - `resilience: AgentResilience` (keyword-only, required) — forwarded to `stream_subprocess`,
    which reads the spawn-retry and watchdog-grace knobs off it. Every timing bound in the runner
    arrives this way rather than from an import-time env constant.
  - `cwd=None` (keyword-only) — the subprocess working directory, forwarded to
    `stream_subprocess`.
  - `env_extra=None` (keyword-only) — extra environment layered over the inherited one, forwarded
    to `stream_subprocess`. This is how a harness's operator-configured `[harness.<backend>].env`
    block reaches the CLI process.
- **Output:** [`TurnState`](finalize-turn.md#turnstate) — one struct, not a tuple. `result_text` and
  `session_id` are whatever `on_event` populated; `diagnostics` holds every non-JSON line and every
  diagnostic `on_event` appended; `timed_out` is `True` when `stream_subprocess` timed out/was
  watchdog-killed **or** an [early abort](#early-abort) fired;
  `returncode` is the child's exit code verbatim.
- **Raises:** nothing turn-specific — a `stream_subprocess` `Popen` failure propagates as its
  normal `OSError`.

> **Both `cwd` and `env_extra` are honoured here.** `cwd` was previously accepted and silently
> dropped, so Codex/Copilot/OpenCode nodes always ran in the launching process's working directory
> regardless of what the node asked for. It is threaded through now.

## Algorithm

1. Initialize `state = TurnState()` and `early_abort = [""]` (a single-element list so the nested
   `on_line` closure can mutate it; the string it holds names *which* abort fired).
2. Define `on_line(raw: str) -> bool`, the per-line callback handed to
   [`stream_subprocess`](stream-subprocess.md#algorithm):
   1. Strip `raw`; an empty stripped line is a no-op (`return False`).
   2. Record `before = len(state.diagnostics)`.
   3. `json.loads(line)`:
      - **Parse succeeds** → call `on_event(event, state, node_id)`; the backend's callback is
        responsible for any printing and for anything it wants to add to `state.diagnostics`.
      - **Parse fails** (`JSONDecodeError`) → print `[{node_id}] {line}` and append the raw line to
        `state.diagnostics` verbatim (a CLI's plain-text log line, e.g. opencode's `--print-logs`
        output, still reaches the classifier).
   4. **Scan only what this line added** — `new_diag = "\n".join(state.diagnostics[before:])` — and
      run the [early-abort](#early-abort) checks against it.
   5. Otherwise `return False` (keep reading).
3. Call `stream_subprocess(cmd, node_id, timeout, on_line, resilience=resilience,
   stdin_data=stdin_data, cwd=cwd, env_extra=env_extra)` → `(timed_out, returncode)`.
4. Set `state.timed_out = timed_out or bool(early_abort[0])` and `state.returncode = returncode`,
   then return `state`. The `or` folds the early-abort signal into `timed_out`, because
   `stream_subprocess` reports only its *own* in-loop/watchdog triggers there — a truthy `on_line`
   return kills the process identically but is not itself reported back as "timed out", so
   `stream_jsonl` re-derives that meaning from `early_abort`.

The read loop itself is not here: line reading, timeout, watchdog, and process-group kill all live
in `stream_subprocess`. `stream_jsonl` is that loop's **rule set**, invoked once per line.

## Early abort

Two checks run against each line's newly-added diagnostics, in order, and either one returns `True`
from `on_line` — [`stream_subprocess`](stream-subprocess.md)'s early-abort contract, treated
identically to a timeout: the read loop breaks and the process group is killed.

1. **[`is_cap(new_diag)`](classify-turn.md#is_cap)** → `early_abort[0] = "cap"`. A spending-cap or
   usage-limit marker means waiting is the only recovery, and it is a *scheduled* wait — the run
   should start it now rather than after the CLI's internal retries expire.
2. **[`is_transient(new_diag)`](classify-turn.md#is_transient)** → `early_abort[0] = "transient"`.
   A recoverable provider failure (OpenCode's `ProviderHeaderTimeoutError` is the standing example)
   means workhorse's own bounded backoff should own the retry, not the CLI's internal loop.

Both markers can arrive either un-parsed (the JSON-decode-fails branch, e.g. opencode's raw
`--print-logs` ERROR line) or structured (an `on_event` implementation appends it to
`state.diagnostics` from a parsed error event) — the checks run after either path, so both are
caught identically. Scanning only the newly-added slice keeps the whole stream `O(n)` rather than
re-scanning everything already seen; that is why `TurnState.diagnostics` is a list and
`diagnostics_text` a joining property, not a pre-joined string.

Without these checks a mid-stream failure would block until the CLI's own retry gives up or the
[watchdog](stream-subprocess.md#timeout-enforcement) force-kills the process after
`timeout + grace` — tens of minutes of dead time on an unattended run. Aborting immediately means
[`classify_turn`](classify-turn.md#ladder-first-match-wins) sees `timed_out=True` with the marker
still in the diagnostics, and its first two ladder branches recover the true cause: a cap is
reported as a cap (`test_opencode_cap_log_line_aborts_stream_early` asserts the error says "cap
reached", not "Timeout waiting for result"), and a transient provider error is reported as a
transient provider failure rather than as a node-budget overrun.

## Related pieces

- [`stream_subprocess`](stream-subprocess.md) — the supervised-spawn path `stream_jsonl` streams
  every JSONL backend's CLI turn through; owns the actual process spawn, line reads, timeout, and
  group-kill.
- [`finalize_turn`](finalize-turn.md) — the next call in every JSONL backend's `run_turn`, turning
  the returned `TurnState` into the turn's result text or a raised `BackendInvocationError`.
- [`TurnState`](finalize-turn.md#turnstate) — the struct this function fills and returns; shared
  with the aider text path so both classify through one signature.
- [`is_cap`](classify-turn.md#is_cap) / [`is_transient`](classify-turn.md#is_transient) — the
  marker predicates the early-abort checks reuse, so this early exit and `classify_turn`'s own
  detection can never disagree about what a line means.
- [`_codex_on_event`](codex-on-event.md) — the `on_event` implementation for `CodexBackend`, giving
  `stream_jsonl` its codex-specific vocabulary (`thread.started`/`item.completed`/error events).
- [`_copilot_on_event`](copilot-on-event.md) — the `on_event` implementation for `CopilotBackend`,
  giving `stream_jsonl` its copilot-specific vocabulary (`assistant.message`/`result`/error
  events).
- [`_opencode_on_event`](opencode-on-event.md) — the `on_event` implementation for
  `OpenCodeBackend`, giving `stream_jsonl` its opencode-specific vocabulary (`text`/`error`
  events, and unconditional per-line `sessionID` capture).
