---
type: concept
slug: finalize-turn
title: finalize_turn — where every non-Claude turn ends
---
# finalize_turn — where every non-Claude turn ends

The single call every non-Claude backend makes to turn a finished subprocess turn into a result or
a raised error: it reports the turn's token/cost usage to the open telemetry span, then delegates
the verdict to [`classify_turn`](classify-turn.md) so the four JSONL backends (via
[`stream_jsonl`](stream-jsonl.md)) classify through the exact same ladder the Claude path uses,
producing identical failure messages and transient/overflow/cap/non-recoverable verdicts regardless
of which CLI ran. It owns no classification rules of its own.

It lives in `runner/backends/turn.py` together with [`TurnState`](#turnstate), because the two are
halves of one contract: what a streaming turn accumulates, and how that accumulation becomes a
result or a `BackendInvocationError`. Nothing in that module names a CLI.

- code: `workhorse/workhorse/runner/backends/turn.py::finalize_turn`
- verify: `workhorse/tests/test_backends.py::test_finalize_turn_classifies_failures`,
  `workhorse/tests/test_backends.py::test_finalize_turn_non_recoverable_names_each_backend`

## Contract

- **Input:**
  - `backend_name` — the CLI's registry name (`"codex"`, `"copilot"`, `"opencode"`, or
    [`"cline"`](cline-backend.md)), forwarded to `classify_turn` so its error messages name the
    right CLI.
  - `node_id` — the workflow node this turn belonged to, forwarded verbatim.
  - `state: TurnState` — the [struct](#turnstate) the caller accumulated during the turn
    (`stream_jsonl`'s per-line loop plus the backend's `on_event`). **One argument, not four:**
    `result_text`, `session_id`, `diagnostics`,
    `timed_out` and `returncode` are all read off it here.
  - `session_id_path` — where `classify_turn` persists `state.session_id` on success or overflow,
    forwarded verbatim.
  - `timeout` — **positional and required**; the budget that was in effect, echoed into a timeout
    error message. There is no module-constant default: the caller passes the budget it was given.
  - `rate_reset_at=None` — an out-of-band unix epoch for when a cap's window reopens (the
    opencode/Codex path's [`_codex_reset_at`](codex-reset-at.md) probe fetches this outside the
    event stream, since opencode drops the reset headers on its headless path); on a cap the
    classifier attaches it to the raised error so the runner sleeps until exactly then instead of
    the blind default wait.
- **Output:** `str` — the turn's result text on success, identical to what `classify_turn` returns.
- **Raises:** `BackendInvocationError`, exactly as classified by
  [`classify_turn`](classify-turn.md#ladder-first-match-wins) — this function adds no error paths of
  its own.

## Algorithm

```python
if not state.usage.is_empty:
    otel.turn_result(state.usage)
return _failure.classify_turn(
    backend_name, node_id,
    result_text=state.result_text, diagnostics=state.diagnostics_text,
    timed_out=state.timed_out, returncode=state.returncode, timeout=timeout,
    session_id=state.session_id, session_id_path=session_id_path,
    rate_reset_at=rate_reset_at,
)
```

1. **Report usage, if the turn reported any.** This is the one place every non-Claude turn ends, so
   it is where a turn's normalized token counts and cost reach the open agent-turn span — no
   backend needs its own `otel` call, and a *new* backend gets cost/token attribution by populating
   `state.usage` and nothing else. The `is_empty` guard is load-bearing: a harness that reports no
   usage must leave the attributes **absent**, not zero, because averaging a real zero together
   with an unknown understates spend.
2. **Delegate the verdict.** Every remaining argument is unpacked from `state` and handed to
   `classify_turn`, which owns every classification rule — see its
   [ladder](classify-turn.md#ladder-first-match-wins). `diagnostics` comes from
   [`state.diagnostics_text`](#turnstate), the newline-joined form of the accumulated list.

## `TurnState`

What one non-Claude turn yielded, as its output streamed past — a `@dataclass(slots=True)` in the
same module. Mutable by construction: `stream_jsonl`'s per-line callback and the per-CLI `on_event`
adapter write into it event by event, the process outcome lands once the stream closes, and
`finalize_turn` reads the finished value.

- code: `workhorse/workhorse/runner/backends/turn.py::TurnState`

| Field | Default | Meaning |
| --- | --- | --- |
| `result_text: str` | `""` | the turn's final answer text, as the backend's `on_event` recognised it |
| `session_id: str \| None` | `None` | the CLI's session id for this turn, for a later `--resume` |
| `usage: TurnUsage` | empty | normalized token/cost counts (`runner/usage.py`), reported in step 1 above |
| `diagnostics: list[str]` | `[]` | anything signalling *how* a turn failed — non-JSON output lines and structured error events — for `classify_turn` to scan |
| `timed_out: bool` | `False` | the turn did not end on its own (watchdog kill, or an early abort) |
| `returncode: int` | `0` | the subprocess's exit code |

`diagnostics_text` is a read-only property returning `"\n".join(self.diagnostics)` — the single
string `classify_turn` scans. Diagnostics accumulate as a list so
[`stream_jsonl`](stream-jsonl.md#early-abort) can scan only the slice
a single line added, rather than re-joining everything seen so far on every line.

Two design rules hold this struct in place:

- **It replaces a bare `dict`** that four backends `setdefault`-ed into with no shared declaration,
  and the four-element tuple that used to carry the same values back out. A field is now declared
  once, in one place, with a type.
- **Every field here is one *every* backend has.** A key only one CLI needs does not belong on the
  struct they all share — opencode's per-turn text-part bookkeeping lives in its own
  `_OpenCodeEvents` rather than here.

## Related pieces

- [`classify_turn`](classify-turn.md) — the function this one delegates its verdict to; owns every
  transient/overflow/cap/non-recoverable rule. `finalize_turn` exists so its four JSONL callers
  don't each reshape their own state into `classify_turn`'s keyword-only signature independently —
  and so usage telemetry has exactly one emission point.
- [`stream_jsonl`](stream-jsonl.md) — produces the `TurnState` this function consumes, for
  `CodexBackend`, `CopilotBackend`, `ClineBackend` and `OpenCodeBackend`.
- [`read_session_id`](read-session-id.md) — the reader for what `classify_turn` persists here; the
  other half of the session-resume loop.
- [`_codex_reset_at`](codex-reset-at.md) — `OpenCodeBackend.run_turn`'s out-of-band probe for the
  precise Codex-provider cap reset epoch, passed through as this function's `rate_reset_at` when
  the turn's diagnostics look like a cap.
