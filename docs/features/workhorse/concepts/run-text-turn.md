---
type: concept
slug: run-text-turn
title: _run_text_turn — the plain-text turn runner
---
# _run_text_turn — the plain-text turn runner

The turn runner for backends with no event protocol — today just
[`AiderBackend`](aider-backend.md) (`aider --message`), which streams a plain-text transcript
instead of newline-delimited JSON. Where [`stream_jsonl`](stream-jsonl.md) hands each parsed line
to an `on_event` callback, `_run_text_turn` has nothing to parse: every line **is** the result, so
it echoes and accumulates the raw stream verbatim through
[`stream_subprocess`](stream-subprocess.md), then hands the joined transcript to
[`finalize_turn`](finalize-turn.md) as both the result text and the diagnostics — a CLI's overflow
and transient markers appear inline in its own text output, so the classifier finds them there
instead of in a separate error channel.

It lives in `runner/backends/aider.py`, beside its only caller, rather than in a shared module. A
port package whose shared modules hold one implementation's mechanics is exactly the shape
`runner/backends/` avoids: [`jsonl.py`](stream-jsonl.md) and [`turn.py`](finalize-turn.md) are
shared because three backends use them, and this loop is not because one does.

- code: `workhorse/workhorse/runner/backends/aider.py::_run_text_turn`
- verify: `workhorse/tests/test_backends.py::test_aider_run_turn_builds_noninteractive_cmd`

## Contract

- **Input** — six positional, then keyword-only:
  - `backend_name: str` — the classifier tag (`"aider"`), forwarded to
    [`finalize_turn`](finalize-turn.md) so its error messages name the right CLI.
  - `cmd: list[str]` — the argv to spawn, passed straight through to
    [`stream_subprocess`](stream-subprocess.md#contract).
  - `node_id: str` — the workflow node id; used only for the `[{node_id}] ...` log-line prefix and
    forwarded to `stream_subprocess`.
  - `timeout: float` — forwarded verbatim to `stream_subprocess`.
  - `cwd: str | None` — forwarded to `stream_subprocess` as the subprocess working directory.
  - `session_id_path: Path | None` — forwarded to [`finalize_turn`](finalize-turn.md). Aider has no
    resumable session, so `TurnState.session_id` is always `None` and this path is only ever used
    to *clear* a stale id, never to persist a new one.
  - `resilience: AgentResilience` (keyword-only, required) — forwarded to `stream_subprocess`,
    which reads the spawn-retry and watchdog-grace knobs off it. Every timing bound arrives this
    way rather than from an import-time env constant.
  - `env_extra=None` (keyword-only) — extra environment layered over the inherited one, forwarded
    to `stream_subprocess`; this is how `[harness.aider].env` reaches the CLI process.
- **Output:** `str` — the final result text, or a raised
  [`BackendInvocationError`](classify-turn.md#backendinvocationerror) (via
  [`finalize_turn`](finalize-turn.md)'s classification) when the transcript doesn't count as a
  usable answer.
- **Raises:** nothing turn-specific — a `stream_subprocess` `Popen` failure propagates as its
  normal `OSError`.

## Algorithm

1. Initialize `lines: list[str] = []`.
2. Define `on_line(raw: str) -> None`, the per-line callback handed to
   [`stream_subprocess`](stream-subprocess.md#algorithm): strip the trailing newline, print
   `[{node_id}] {line}` (live echo, matching every other backend's log format), and append the
   line to `lines`. Unlike [`stream_jsonl`'s `on_line`](stream-jsonl.md#algorithm) this returns
   `None`, never a truthy early-abort signal — a plain-text backend has no structured cap marker to
   detect mid-stream, so a cap only surfaces after the process exits, via
   [`finalize_turn`](finalize-turn.md)'s diagnostics scan.
3. Call `stream_subprocess(cmd, node_id, timeout, on_line, resilience=resilience, cwd=cwd,
   env_extra=env_extra)` → `(timed_out, returncode)`. No `stdin_data` — aider takes its prompt as a
   `--message` argv element, not on stdin.
4. Join `lines` with `"\n"` and `.strip()` into `text` — the whole transcript, in order.
5. Build the shared [`TurnState`](finalize-turn.md#turnstate):
   ```python
   state = TurnState(
       result_text=text,
       diagnostics=[text],
       usage=_usage.from_text(text),
       timed_out=timed_out,
       returncode=returncode,
   )
   ```
   `result_text` and the single `diagnostics` entry are **the same string**: the transcript is both
   the answer and the only signal the classifier has for overflow/transient markers.
6. Return `finalize_turn(backend_name, node_id, state, session_id_path, timeout)` — five
   positional arguments, the same call every JSONL backend makes.

### Usage from the transcript

`usage.from_text(text)` is what keeps aider's turns comparable with the JSONL backends'. Aider
reports consumption in prose, ending a turn with a line like
`Tokens: 3.4k sent, 213 received. Cost: $0.0123 message, $0.05 session.`, so there is no event to
[normalize](stream-jsonl.md) — the transcript is parsed instead, by a deliberately best-effort
regex. **Last report wins:** a multi-step turn reprints the line and the final one is the turn's
total. No match simply yields an empty `TurnUsage`, and
[`finalize_turn`](finalize-turn.md#turnstate) then emits no usage attributes at all rather than a
fabricated zero.

## Related pieces

- [`stream_subprocess`](stream-subprocess.md) — the supervised-spawn path `_run_text_turn` streams
  aider's CLI turn through; owns the actual process spawn, line reads, timeout, and group-kill.
- [`stream_jsonl`](stream-jsonl.md) — the sibling turn runner for the three JSONL-speaking
  backends; `_run_text_turn` is its plain-text counterpart, sharing the same
  `stream_subprocess`/[`finalize_turn`](finalize-turn.md) bracketing and returning the same
  `TurnState`, but with no event parsing and no early-abort scan.
- [`finalize_turn`](finalize-turn.md) — the classifier `_run_text_turn` calls with a `TurnState`
  whose `result_text` and lone diagnostic are the identical transcript string, turning it into the
  turn's result text or a raised `BackendInvocationError`.
- [`AiderBackend`](aider-backend.md) — the sole caller, which builds aider's non-interactive `cmd`
  and delegates the actual streaming here.
