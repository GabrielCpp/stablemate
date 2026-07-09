---
type: concept
slug: run-text-turn
title: _run_text_turn — the plain-text turn runner
---
# _run_text_turn — the plain-text turn runner

The turn runner for backends with no event protocol — today just
[`AiderBackend`](aider-backend.md) (`aider --message`), which streams a plain-text
transcript instead of newline-delimited JSON. Where [`_stream_jsonl`](stream-jsonl.md) hands each parsed
line to an `on_event` callback, `_run_text_turn` has nothing to parse: every line **is** the
result, so it echoes and accumulates the raw stream verbatim through
[`stream_subprocess`](stream-subprocess.md), then hands the joined transcript to
[`_finalize_turn`](finalize-turn.md) as both the result text and the diagnostics — a CLI's overflow/
transient markers appear inline in its own text output, so the classifier finds them there instead
of in a separate error channel.

- code: `workhorse/workhorse/runner/backends.py::_run_text_turn`

## Contract

- **Input:**
  - `backend_name: str` — the classifier tag (`"aider"`), forwarded to
    [`_finalize_turn`](finalize-turn.md) so its error messages name the right CLI.
  - `cmd: list[str]` — the argv to spawn, passed straight through to
    [`stream_subprocess`](stream-subprocess.md#contract).
  - `node_id: str` — the workflow node id; used only for the `[{node_id}] ...` log-line prefix and
    forwarded to `stream_subprocess`.
  - `timeout: float` — forwarded verbatim to `stream_subprocess`.
  - `cwd: str | None` — forwarded to `stream_subprocess` as the subprocess working directory.
  - `session_id_path: Path | None` — forwarded to [`_finalize_turn`](finalize-turn.md); aider has no
    resumable session, so this is always used to *clear* a stale one, never to persist a new id
    (`state["session_id"]` is always `None`).
- **Output:** `str` — the final result text, or a raised `agent.BackendInvocationError` (via
  [`_finalize_turn`](finalize-turn.md)'s classification) when the transcript doesn't count as a
  usable answer.
- **Raises:** nothing turn-specific — a `stream_subprocess` `Popen` failure propagates as its
  normal `OSError`.

## Algorithm

1. Initialize `lines: list[str] = []`.
2. Define `on_line(raw: str) -> None`, the per-line callback handed to
   [`stream_subprocess`](stream-subprocess.md#algorithm): strip the trailing newline, print
   `[{node_id}] {line}` (live echo, matching every other backend's log format), and append the
   line to `lines`. Unlike [`_stream_jsonl`'s `on_line`](stream-jsonl.md#algorithm) this never
   returns a truthy early-abort signal — plain-text backends have no structured cap marker to
   detect mid-stream, so a cap only surfaces after the process exits, via
   [`_finalize_turn`](finalize-turn.md)'s diagnostics scan.
3. Call `stream_subprocess(cmd, node_id, timeout, on_line, cwd=cwd)` → `(timed_out, returncode)`
   (no `stdin_data` — aider takes its prompt as a `--message` argv element, not on stdin).
4. Join `lines` with `"\n"` and `.strip()` into `text` — the whole transcript, in order.
5. Build `state = {"result_text": text, "session_id": None}`.
6. Return `_finalize_turn(backend_name, node_id, state, text, timed_out, returncode,
   session_id_path, timeout)` (see [`_finalize_turn`](finalize-turn.md)) — note `diagnostics` and
   `result_text` are **the same string**: the transcript is both the answer and the only signal the
   classifier has for overflow/transient markers.

## Related pieces

- [`stream_subprocess`](stream-subprocess.md) — the supervised-spawn path `_run_text_turn` streams
  aider's CLI turn through; owns the actual process spawn, line reads, timeout, and group-kill.
- [`_stream_jsonl`](stream-jsonl.md) — the sibling turn runner for the three JSONL-speaking
  backends; `_run_text_turn` is its plain-text counterpart, sharing the same
  `stream_subprocess`/[`_finalize_turn`](finalize-turn.md) bracketing but with no event parsing or
  cap-abort scan.
- [`_finalize_turn`](finalize-turn.md) — the classifier `_run_text_turn` calls with `result_text`
  and `diagnostics` set to the identical transcript string, turning it into the turn's result text
  or a raised `BackendInvocationError`.
- [`AiderBackend`](aider-backend.md) — the sole caller, which builds aider's non-interactive `cmd`
  and delegates the actual streaming to `_run_text_turn`.

