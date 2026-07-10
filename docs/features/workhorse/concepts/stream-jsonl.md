---
type: concept
slug: stream-jsonl
title: _stream_jsonl — the shared JSONL event loop
---
# _stream_jsonl — the shared JSONL event loop

The generic newline-delimited-JSON turn runner shared by the three JSONL-speaking backends —
`CodexBackend`, `CopilotBackend`, `OpenCodeBackend` (`workhorse/workhorse/runner/backends.py`).
Each backend builds its own `cmd` and supplies an `on_event` callback that knows its CLI's own
event vocabulary (`_codex_on_event`, `_copilot_on_event`, `_opencode_on_event`); `_stream_jsonl`
owns everything vocabulary-agnostic: spawning through [stream_subprocess](stream-subprocess.md),
per-line JSON parsing, non-JSON passthrough, and the early-abort-on-cap scan. A backend's
`run_turn` calls it once, then hands the returned `(state, diagnostics, timed_out, returncode)` to
[`_finalize_turn`](finalize-turn.md) to classify the turn the same way every other backend does.

- code: `workhorse/workhorse/runner/backends.py::_stream_jsonl`
- verify: `workhorse/tests/test_backends.py::test_opencode_cap_log_line_aborts_stream_early`,
  `workhorse/tests/test_backends.py::test_opencode_cap_structured_error_event_aborts_stream_early`

## Contract

- **Input:**
  - `cmd: list[str]` — the argv to spawn, passed straight through to
    [`stream_subprocess`](stream-subprocess.md#contract).
  - `node_id: str` — the workflow node id; used only for log-line prefixes
    (`[{node_id}] ...`) and forwarded to `stream_subprocess`/`on_event`.
  - `timeout: float` — forwarded verbatim to `stream_subprocess`.
  - `stdin_data: str | None` — forwarded verbatim to `stream_subprocess` (a single-shot prompt on
    stdin, e.g. Codex's resume-with-prompt invocation; `None` for Copilot, which takes its prompt
    as a `-p` arg).
  - `on_event` — a `(event: dict, state: dict, node_id: str, diagnostics: list) -> None`
    callback, invoked once per successfully parsed JSON object as
    `on_event(event, state, node_id, diagnostics)`; mutates `state` and `diagnostics` in place (no
    return value). The three concrete implementations are `_codex_on_event`, `_copilot_on_event`,
    `_opencode_on_event` (each documented under its own backend).
  - `cwd: str | None` (default `None`) — forwarded to `stream_subprocess` as the subprocess
    working directory.
- **Output:** `tuple[dict, str, bool, int]` — `(state, diagnostics, timed_out, returncode)`:
  - `state: dict` — starts as `{"result_text": "", "session_id": None}`; `on_event` implementations
    populate both keys as their CLI's events arrive.
  - `diagnostics: str` — every non-JSON line and every diagnostic `on_event` appended, newline-joined.
  - `timed_out: bool` — `True` when `stream_subprocess` timed out/was watchdog-killed **or** the
    cap-abort path fired (see [Cap abort](#cap-abort-early-exit-on-a-spending-capusage-limit)).
  - `returncode: int` — the child's exit code, verbatim from `stream_subprocess`.
- **Raises:** nothing turn-specific — a `stream_subprocess` `Popen` failure propagates as its
  normal `OSError`.

## Algorithm

1. Initialize `state = {"result_text": "", "session_id": None}`, `diagnostics = []`, and
   `cap_abort = [False]` (single-element list so the nested `on_line` closure can mutate it).
2. Define `on_line(raw: str) -> bool`, the per-line callback handed to
   [`stream_subprocess`](stream-subprocess.md#algorithm):
   1. Strip `raw`; an empty stripped line is a no-op (`return False`).
   2. Record `before = len(diagnostics)`.
   3. `json.loads(line)`:
      - **Parse succeeds** → call `on_event(event, state, node_id, diagnostics)`; the backend's
        callback is responsible for any printing/diagnostics it wants to add.
      - **Parse fails** (`JSONDecodeError`) → print `[{node_id}] {line}` and append the raw line to
        `diagnostics` verbatim (a CLI's plain-text log line, e.g. opencode's `--print-logs`
        output, still reaches the classifier).
   4. **Cap abort — early exit on a spending-cap/usage-limit marker.** Join only the diagnostics
      lines *this call* added (`diagnostics[before:]`) into `new_diag`; if `cap_abort[0]` is still
      `False` and `new_diag` is non-empty and [`_is_cap(new_diag)`](classify-turn.md#_is_cap)
      matches, set `cap_abort[0] = True` and `return True`. A cap marker can arrive either
      un-parsed (the JSON-decode-fails branch, e.g. opencode's raw `--print-logs` ERROR line) or
      structured (an `on_event` implementation appends it to `diagnostics` from a parsed error
      event) — this check runs after either path, so both are caught identically. Returning `True`
      is `stream_subprocess`'s early-abort signal: the read loop breaks immediately and the process
      group is killed, instead of blocking for the CLI's own internal retry window (observed up to
      the full `timeout`) while the watchdog would otherwise eventually reap it. Scanning only the
      newly-added slice keeps the check `O(n)` over the whole stream rather than re-scanning
      everything already seen.
      - Otherwise `return False` (keep reading).
   5. This is the **read loop rewritten as a rule set**, not a spawn: line reading, timeout,
      watchdog, and process-group kill all live in `stream_subprocess` itself; `_stream_jsonl`
      never sees them directly, only invokes each `on_line` decision.
3. Call `stream_subprocess(cmd, node_id, timeout, on_line, stdin_data=stdin_data, cwd=cwd)` →
   `(timed_out, returncode)`.
4. Return `(state, "\n".join(diagnostics), timed_out or cap_abort[0], returncode)` — the `or`
   folds the cap-abort signal into `timed_out` even though `stream_subprocess`'s own timed-out flag
   only reflects its own in-loop/watchdog triggers, not the caller-supplied `on_line`'s truthy
   return (which `stream_subprocess` treats identically at the process-kill level but does not
   itself report back as "timed out" — `_stream_jsonl` re-derives that meaning from
   `cap_abort[0]`).

## Cap abort — early exit on a spending cap/usage limit

Without this check, a cap hit mid-stream (opencode/Codex/Copilot each surface it differently —
a raw log line, a structured error event) would otherwise block until the CLI's own internal retry
gives up or the [watchdog](stream-subprocess.md#timeout-enforcement) force-kills the process after
`timeout + _WATCHDOG_GRACE_S` — tens of minutes of dead time on an unattended run. Detecting the
marker as soon as it appears and returning `True` from `on_line` reuses `stream_subprocess`'s
existing early-abort contract (a truthy `on_line` return is treated identically to a timeout: the
read loop breaks and the process group is killed) so the runner can start waiting out the cap's
reset window immediately instead. The downstream classifier
([`classify_turn`](classify-turn.md)) sees `timed_out=True` with cap-marker diagnostics and reports
a cap, not a plain timeout — see `test_opencode_cap_log_line_aborts_stream_early`'s assertion that
the resulting error says "cap reached", not "Timeout waiting for result".

## Related pieces

- [`stream_subprocess`](stream-subprocess.md) — the supervised-spawn path `_stream_jsonl` streams
  every JSONL backend's CLI turn through; owns the actual process spawn, line reads, timeout, and
  group-kill.
- [`_finalize_turn`](finalize-turn.md) — the classifier every JSONL backend's `run_turn` calls
  immediately after `_stream_jsonl` returns, turning `(state, diagnostics, timed_out, returncode)`
  into the turn's result text or a raised `BackendInvocationError`.
- [`_is_cap`](classify-turn.md#_is_cap) — the marker-substring predicate the cap-abort check
  reuses so `_stream_jsonl`'s early exit and `classify_turn`'s own cap detection agree on what
  counts as a cap.
- [`_codex_on_event`](codex-on-event.md) — the `on_event` implementation for `CodexBackend`, giving
  `_stream_jsonl` its codex-specific vocabulary (`thread.started`/`item.completed`/error events).
- [`_copilot_on_event`](copilot-on-event.md) — the `on_event` implementation for `CopilotBackend`,
  giving `_stream_jsonl` its copilot-specific vocabulary (`assistant.message`/`result`/error
  events).
- [`_opencode_on_event`](opencode-on-event.md) — the `on_event` implementation for
  `OpenCodeBackend`, giving `_stream_jsonl` its opencode-specific vocabulary (`text`/`error`
  events, and unconditional per-line `sessionID` capture).
