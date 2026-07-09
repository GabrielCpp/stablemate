---
type: concept
slug: classify-turn
title: classify_turn — the shared backend-failure classifier
---
# classify_turn — the shared backend-failure classifier

The single source of truth for turning a finished agent-CLI subprocess into either a result string
or a typed [`BackendInvocationError`](#backendinvocationerror) — shared by the Claude path
(`_run_claude_cli`) and the JSONL/text path ([`_finalize_turn`](finalize-turn.md))
so every backend produces identical failure messages and the same transient / cap / overflow /
non-recoverable verdict, regardless of which CLI ran. Its callers feed the resulting error into
[`run_agent`](run-agent.md)'s [ladder](run-agent.md#the-ladder), which decides whether to wait,
compact, reframe, or default based on the flags this function sets.

- code: `workhorse/workhorse/runner/agent.py::classify_turn`
- verify: `workhorse/tests/test_agent_cap.py::test_classification`,
  `workhorse/tests/test_agent_cap.py::test_cap_hang_classified_as_cap_not_timeout`,
  `workhorse/tests/test_backends.py::test_finalize_turn_classifies_failures`,
  `workhorse/tests/test_backends.py::test_finalize_turn_non_recoverable_names_each_backend`,
  `workhorse/tests/test_backends.py::test_opencode_cap_log_line_aborts_stream_early`,
  `workhorse/tests/test_agent_recovery.py::test_context_overflow_is_detected`

## Contract

- **Input:**
  - `backend_name: str` — the running CLI's name (`"claude"`, `"codex"`, `"copilot"`, `"aider"`,
    `"opencode"`), interpolated into every error message so a shared classifier never hardcodes
    one backend.
  - `node_id: str` — the workflow node this turn belonged to, interpolated into every message.
  - `result_text: str | None` — the turn's captured result text, or `None`/empty if none arrived.
  - `diagnostics: str` — non-result output captured during the turn (raw log lines, error-result
    subtypes) that the marker scans below search for cap/transient/overflow signals.
  - `timed_out: bool` — `True` if [`stream_subprocess`](run-agent.md#related-pieces)'s in-loop
    check or watchdog killed the turn for exceeding its wall-clock budget.
  - `returncode: int` — the subprocess's exit code.
  - `timeout: float` (default `DEFAULT_RESULT_TIMEOUT_S`) — the budget that was in effect, echoed
    into the timeout error message.
  - `session_id: str | None` (default `None`) — the backend's session id for this turn, if any.
  - `session_id_path: Path | None` (default `None`) — where to persist `session_id`; `None`
    disables persistence.
  - `rate_limited: bool` (default `False`) — a structured cap signal (Claude's `rate_limit_event`,
    via `_rate_limit_info`) saying the limit was actually hit, independent of the text markers
    below.
  - `rate_reset_at: float | None` (default `None`) — a unix epoch when the capped window reopens,
    from the same structured signal; attached to the raised error as `reset_at` when the turn is a
    cap.
- **Output:** `str` — `result_text`, returned unchanged on success (after persisting
  `session_id`).
- **Raises:** `BackendInvocationError` on every non-success path, flagged per the ladder below.

## Ladder (first match wins)

```
tail = f": {diagnostics.strip()}" if diagnostics.strip() else ""
is_cap = rate_limited or _is_cap(diagnostics)
cap_reset_at = rate_reset_at if is_cap else None

if is_cap:
    raise BackendInvocationError(f"{backend_name} usage/spending cap reached for node "
                                  f"'{node_id}'{tail}", transient=True, reset_at=cap_reset_at)
if timed_out:
    raise BackendInvocationError(f"Timeout waiting for result from {backend_name} for node "
                                  f"'{node_id}' after {int(timeout)}s{tail}",
                                  transient=True, timed_out=True)
if _is_context_overflow(diagnostics):
    if session_id_path and session_id: session_id_path.write_text(session_id)
    raise BackendInvocationError(f"Context window exhausted for node '{node_id}'{tail}",
                                  transient=False, overflow=True)
if returncode != 0:
    raise BackendInvocationError(f"{backend_name} CLI exited with code {returncode} for node "
                                  f"'{node_id}'{tail}",
                                  transient=_is_transient(diagnostics) or rate_limited,
                                  reset_at=cap_reset_at)
if not result_text:
    raise BackendInvocationError(f"No result text from {backend_name} for node '{node_id}'{tail}",
                                  transient=True, reset_at=cap_reset_at)
if session_id_path and session_id: session_id_path.write_text(session_id)
return result_text
```

1. **Cap marker or structured rate-limit signal → a scheduled-reset cap.** Checked *before*
   `timed_out` because a cap often makes the CLI hang until the watchdog reaps it (e.g. opencode
   logs `"AI_APICallError: The usage limit has been reached"` to its stream but never exits) —
   classifying that as a cap (not a timeout) is what lets the run wait the window out under a
   truthful "cap reached" message instead of a bogus "Timeout waiting for result … after Ns" that
   buries the real cause. `is_cap` is `rate_limited OR _is_cap(diagnostics)`
   (substring match against `_CAP_MARKERS`: `"spending cap"`, `"usage limit"`, `"weekly limit"`,
   `"session limit"`, `"quota"`, `"key limit"`, `"daily limit"`). `transient=True`; `reset_at` is
   `rate_reset_at` when `is_cap` (else `None`, so a non-cap failure can never look like one).
2. **`timed_out` → transient.** The watchdog already reaped the process group by this point; the
   message names the elapsed `timeout` budget. `transient=True`, `timed_out=True` (distinct from
   the cap branch's `timed_out=False`, so the retry loop's budget-overrun warning only fires for a
   genuine wall-clock timeout, not a cap-induced hang).
3. **Context-overflow marker → `overflow`.** `_is_context_overflow(diagnostics)`
   (substring match against `_CONTEXT_OVERFLOW_MARKERS`: `"prompt is too long"`, `"input is too
   long"`, `"context length"`, `"context window"`, `"maximum context"`, `"context limit"`,
   `"exceeds the maximum"`, `"too many tokens"`, `"conversation is too long"`, `"dimension
   limit"`, `"many-image requests"`). The session id is persisted here (if both `session_id_path`
   and `session_id` are set) even though this path raises, so the caller can
   [compact-and-continue](run-agent.md#the-ladder) that same overflowing session rather than losing
   it. `transient=False`, `overflow=True` — not retried with backoff (retrying would just overflow
   again); [`run_agent`](run-agent.md) recovers it by compaction instead.
4. **Non-zero exit → transient *iff* the diagnostics match a retryable marker (or a rate limit
   fired), else non-recoverable.** [`_is_transient(diagnostics)`](#_is_transient) substring-matches
   `_TRANSIENT_MARKERS` (rate/overload/network/5xx/429/timeout text, plus every cap marker — a cap
   is still transient/retryable even though it's classified as a cap first). `reset_at` carries
   `cap_reset_at` in case a cap marker slipped through alongside a non-zero exit. A non-matching
   exit is raised with `transient=False, overflow=False` — deterministic (a crashed CLI, a bad
   flag) and NOT retried; [`run_agent`](run-agent.md#the-ladder)'s non-recoverable fast path
   re-raises it immediately instead of reframing or defaulting.
5. **Empty `result_text` → transient.** No output at all (e.g. the CLI was interrupted) is treated
   as recoverable and retried.
6. **Success.** `session_id` is persisted (if both `session_id_path` and `session_id` are set) and
   `result_text` is returned unchanged.

A cap-like failure (branches 1 and 4) carries `reset_at` so the runner can sleep until the window
reopens; every other transient (branches 2, 5) leaves `reset_at` unset, so it is never mistaken for
a cap by the caller. `session_id` is persisted on both success (branch 6) and overflow (branch 3) —
overflow because the compaction retry needs the id of the session it's compacting; every other
raised branch leaves the prior persisted session id untouched.

## `BackendInvocationError`

An agent-CLI turn failed (non-zero exit, or no result event) — code:
`workhorse/workhorse/runner/agent.py::BackendInvocationError`, a `RuntimeError` subclass. Fields,
all set only by `classify_turn` (or in tests, directly):

- `transient: bool` (default `False`) — worth retrying with backoff (cap, rate limit, overload,
  network, timeout, empty result) versus deterministic (`False`, e.g. a crashed CLI) which should
  fail fast.
- `overflow: bool` (default `False`) — the model's context window was exhausted mid-node; recovered
  by [compacting the session and continuing](run-agent.md#the-ladder), not by backoff retry.
- `timed_out: bool` (default `False`) — the turn was killed for exceeding its wall-clock timeout
  (not a rate limit or network blip); the retry loop uses this to warn the next attempt how much it
  overran, so it can size its work to fit (see `_timeout_retry_prompt`).
- `reset_at: float | None` (default `None`) — unix epoch when a capped window reopens, from the
  CLI's structured `rate_limit_event`; set only on cap-like failures. `run_agent`'s invocation layer
  sleeps until this instant when present, more precise than parsing "resets 11:30am" out of the
  message text.

## `_is_cap`

The marker-substring predicate that decides branch 1 of the [ladder](#ladder-first-match-wins): is
this failure a **scheduled-reset cap** (spending/usage/weekly/session/quota — clears on a schedule,
not in seconds) rather than a short transient like a rate limit or overload?

- code: `workhorse/workhorse/runner/agent.py::_is_cap`

- **Input:** `diagnostics: str` — the same non-result output `classify_turn` scans for every
  marker check.
- **Output:** `bool` — `True` iff `diagnostics`, lowercased, contains any of `_CAP_MARKERS`:
  `"spending cap"`, `"usage limit"`, `"weekly limit"`, `"session limit"`, `"quota"`, `"key limit"`,
  `"daily limit"`.
- **Algorithm:** lowercase `diagnostics` once (`low = diagnostics.lower()`), then
  `any(marker in low for marker in _CAP_MARKERS)` — a plain substring scan, no regex.

Every `_CAP_MARKERS` entry is also present in `_TRANSIENT_MARKERS`, so a cap-worthy diagnostic
always also reads as transient; `classify_turn` checks `is_cap = rate_limited or _is_cap(diagnostics)`
**before** the `timed_out` branch specifically so a cap that manifests as a hang (the CLI never
exits, so the watchdog sets `timed_out=True`) is still classified as a cap and not mis-framed as a
plain timeout — see [Ladder step 1](#ladder-first-match-wins).

## `_is_transient`

The marker-substring predicate that decides branch 4 of the [ladder](#ladder-first-match-wins): does
a **non-zero-exit** failure look retryable (a rate limit, overload, network blip, 5xx, timeout) or
deterministic (a crashed CLI, a bad flag)?

- code: `workhorse/workhorse/runner/agent.py::_is_transient`
- verify: `workhorse/tests/test_agent_cap.py::test_classification`,
  `workhorse/tests/test_guardrails.py::test_transient_error_detection`

- **Input:** `diagnostics: str` — the same non-result output `classify_turn` scans for every marker
  check.
- **Output:** `bool` — `True` iff `diagnostics`, lowercased, contains any of `_TRANSIENT_MARKERS`:
  every `_CAP_MARKERS` entry (`"spending cap"`, `"usage limit"`, `"weekly limit"`, `"session
  limit"`, `"quota"`, `"key limit"`, `"daily limit"`) plus `"rate limit"`, `"rate-limit"`,
  `"overloaded"`, `"capacity"`, `"temporarily unavailable"`, `"service unavailable"`, `"internal
  server error"`, `"429"`, `"500"`, `"502"`, `"503"`, `"504"`, `"timeout"`, `"timed out"`,
  `"connection reset"`, `"connection error"`, `"econnreset"`, `"etimedout"`, `"network"`.
- **Algorithm:** lowercase `diagnostics` once (`low = diagnostics.lower()`), then
  `any(marker in low for marker in _TRANSIENT_MARKERS)` — a plain substring scan, no regex.

Every `_CAP_MARKERS` entry is included in `_TRANSIENT_MARKERS` by design, so a cap-worthy diagnostic
is always also transient — that's what lets [ladder step 4](#ladder-first-match-wins) write
`transient=_is_transient(diagnostics) or rate_limited` without needing to special-case a cap marker
that slipped past to a non-zero exit (the cap branch, step 1, would already have claimed it first if
`is_cap` matched).

## `_is_context_overflow`

The marker-substring predicate that decides branch 3 of the [ladder](#ladder-first-match-wins): did
this turn fail because the model's context window was exhausted mid-node — the headless CLI
returned instead of auto-compacting — rather than crashing or exiting non-zero for some other
reason?

- code: `workhorse/workhorse/runner/agent.py::_is_context_overflow`
- verify: `workhorse/tests/test_agent_recovery.py::test_context_overflow_is_detected`

- **Input:** `diagnostics: str` — the same non-result output `classify_turn` scans for every marker
  check.
- **Output:** `bool` — `True` iff `diagnostics`, lowercased, contains any of
  `_CONTEXT_OVERFLOW_MARKERS`: `"prompt is too long"`, `"input is too long"`, `"context length"`,
  `"context window"`, `"maximum context"`, `"context limit"`, `"exceeds the maximum"`, `"too many
  tokens"`, `"conversation is too long"`, `"dimension limit"`, `"many-image requests"` — the last
  two cover Claude rejecting a session for too many/too-large images, which the runner also treats
  as overflow so compaction purges the images from context rather than dying as non-recoverable.
- **Algorithm:** lowercase `diagnostics` once (`low = diagnostics.lower()`), then
  `any(marker in low for marker in _CONTEXT_OVERFLOW_MARKERS)` — a plain substring scan, no regex,
  identical shape to [`_is_cap`](#_is_cap) and [`_is_transient`](#_is_transient).

Unlike a cap or a generic transient, an overflow is **not** retried with backoff — retrying the same
prompt on the same full session would just overflow again. `classify_turn` instead marks it
`transient=False, overflow=True` and persists the session id first, so
[`run_agent`](run-agent.md#the-ladder) can [compact that session and continue](compact-session.md)
rather than starting over.

## `_rate_limit_info`

Reads one Claude stream-json `rate_limit_event` into the structured signal `classify_turn` accepts
as its `rate_limited`/`rate_reset_at` inputs — a second, precise cap detector alongside the
text-marker scan ([`_is_cap`](#_is_cap)), since Claude also emits this event on every turn (not just
failing ones) with a machine-readable status and reset time.

- code: `workhorse/workhorse/runner/agent.py::_rate_limit_info`
- verify: `workhorse/tests/test_agent_cap.py::test_rate_limit_info_parsing`

- **Input:** `event: dict` — one parsed `rate_limit_event` stream-json object, of shape
  `{"type": "rate_limit_event", "rate_limit_info": {"status": str, "resetsAt": number, ...}}`.
- **Output:** `tuple[bool, float | None]` — `(blocked, reset_at)`:
  - `blocked: bool` — `True` when `rate_limit_info.status`, lowercased, contains any of
    `_LIMIT_STATUS_MARKERS`: `"block"`, `"reject"`, `"exceed"`, `"throttl"`, `"reached"`,
    `"denied"`, `"over_limit"`, `"limit_reached"`. Deliberately conservative — an unknown or benign
    status (e.g. `"allowed"`) must never be mistaken for a hit, so this is an *additional* signal
    layered on top of the text markers, not a replacement for them.
  - `reset_at: float | None` — `rate_limit_info.resetsAt` coerced to `float`, or `None` if absent or
    not coercible. Populated on *every* event (allowed or blocked), since the window's reset time is
    useful even before the limit is actually hit.
- **Algorithm:**
  1. `info = event.get("rate_limit_info") or {}` — tolerate a missing/`None` key.
  2. `status = str(info.get("status") or "").lower()`.
  3. `blocked = any(marker in status for marker in _LIMIT_STATUS_MARKERS)` — plain substring scan,
     no regex, same shape as [`_is_cap`](#_is_cap)/[`_is_transient`](#_is_transient).
  4. `raw_reset = info.get("resetsAt")`; `reset_at = float(raw_reset)` if not `None`, guarded by a
     `try/except (TypeError, ValueError)` that falls back to `None` on a malformed value (e.g. the
     non-numeric string `"n/a"`) rather than raising.
  5. Return `(blocked, reset_at)`.

Its sole caller, `_stream_events` (`workhorse/workhorse/runner/agent.py`), invokes it once per
`rate_limit_event` line while streaming a Claude turn: it latches `reset_at` into the turn's
`rate_reset_at` accumulator whenever present (last-seen wins, used only if the turn later turns out
to be a cap) and sets `rate_limited = True` for the turn once `blocked` is `True` on any event
(sticky — a later "allowed" event in the same turn does not clear it). Those two accumulated values
are what `_stream_events` returns and `classify_turn` receives as `rate_limited`/`rate_reset_at`,
feeding [ladder step 1](#ladder-first-match-wins)'s `is_cap` check and `reset_at` value.

## Related pieces

- [`run_agent`](run-agent.md) — the caller two levels up; its [ladder](run-agent.md#the-ladder)
  branches on `transient`/`overflow` to decide compact vs. reframe vs. default vs. hard-raise.
- `_run_claude_cli` (`workhorse/workhorse/runner/backends.py`) and
  [`_finalize_turn`](finalize-turn.md) — the two call sites; both run a CLI turn to completion (via
  `stream_subprocess`/`_stream_events`) and pass its raw result into this classifier so every
  backend shares one verdict.
- [`_is_cap`](#_is_cap), [`_is_transient`](#_is_transient), and
  [`_is_context_overflow`](#_is_context_overflow) — the three marker-substring predicates
  `classify_turn` composes into its verdict.
- [`_rate_limit_info`](#_rate_limit_info) — reads a Claude `rate_limit_event` into
  `(blocked, reset_at_epoch)`, the structured signal `_stream_events` forwards as this function's
  `rate_limited`/`rate_reset_at` inputs.
- [GUARDRAILS.md](../../../../workhorse/docs/GUARDRAILS.md) — the operator-facing summary of this
  classifier's recovery ladder and its env-var knobs (`AGENT_CAP_DEFAULT_WAIT_S`,
  `AGENT_CAP_WAIT_MARGIN_S`, `AGENT_CAP_MAX_WAIT_S`, `AGENT_MAX_CAP_WAITS`).
