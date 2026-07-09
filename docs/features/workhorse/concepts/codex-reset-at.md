---
type: concept
slug: codex-reset-at
title: _codex_reset_at — Codex usage-cap reset probe
---
# _codex_reset_at — Codex usage-cap reset probe

Best-effort fetch of the unix epoch when a ChatGPT/Codex subscription's usage window reopens, so a
cap hit through [OpenCodeBackend](opencode-backend.md#contract) can be waited out until its *exact*
reset instead of a blind default wait. OpenCode's own headless `run` path reads the Codex
provider's `x-codex-*` rate-limit response headers for its TUI percentage but **drops them** before
they reach the runner — this function re-requests the same headers directly from the Codex backend,
using the very same OAuth token OpenCode itself uses, mirroring what the `codex` CLI's own usage
display does. It is **best-effort only**: any failure (probe disabled, non-Codex model, missing/
expired OAuth, network/parse error) returns `None`, and the sole caller then falls back to its
default cap wait — this can only ever *sharpen* a wait, never break a run.

- code: `workhorse/workhorse/runner/backends.py::_codex_reset_at`
- verify: `workhorse/tests/test_backends.py::test_codex_reset_at_skips_non_openai_models_without_network`,
  `workhorse/tests/test_backends.py::test_codex_reset_at_disabled_by_env`,
  `workhorse/tests/test_backends.py::test_opencode_cap_attaches_codex_reset_at`,
  `workhorse/tests/test_backends.py::test_opencode_non_cap_does_not_probe_codex`

## Contract

- **Input:**
  - `model: str | None` — the node's resolved model name. Only an `openai/*`-prefixed model (the
    Codex provider on OpenCode) is probed; anything else short-circuits to `None` with no network
    call, since OpenRouter caps on OpenCode go through the daily-key-limit path instead.
  - `timeout: float` (default `15.0`) — seconds before the probe request itself gives up (passed
    straight to `urllib.request.urlopen`).
- **Output:** `float | None` — the `x-codex-primary-reset-at` header value as a unix epoch, or
  `None` on **any** problem: probe disabled, non-Codex model, missing/non-OAuth/expired
  credentials, or a network/parse error during the request.
- **Raises:** nothing — every code path is wrapped so failures degrade to `None`.

## Algorithm

```
if WORKHORSE_CODEX_RESET_PROBE in ("0", "false", "no", ""): return None
if not model or not model.lower().startswith("openai/"): return None
try:
    creds = read ~/.local/share/opencode/auth.json (or $OPENCODE_AUTH_PATH) ["openai"]
    token, account = creds["access"], creds["accountId"]
    if creds["type"] != "oauth" or not token: return None
    POST https://chatgpt.com/backend-api/codex/responses
         body: {model: model minus "openai/" prefix, instructions: "", input: [{role: user,
                content: [{type: input_text, text: "ping"}]}], stream: True, store: False}
         headers: Authorization: Bearer <token>, ChatGPT-Account-Id: <account>,
                  Content-Type: application/json, originator: opencode, User-Agent: opencode,
                  OpenAI-Beta: responses=experimental
    on success: read response headers, close without draining the stream
    on HTTPError: read headers off the exception (a 429 carries the same x-codex-* headers)
    raw = headers.get("x-codex-primary-reset-at")
    return float(raw) if raw else None
except Exception:
    return None
```

1. **Env-var kill switch.** `WORKHORSE_CODEX_RESET_PROBE` (default `"1"`) checked
   case-insensitively against `"0"`/`"false"`/`"no"`/`""` — any of those disables the probe
   entirely, returning `None` before touching the filesystem or network.
2. **Model gate.** `model` must be truthy and start with `"openai/"` (case-insensitive) — the
   Codex provider's model-naming convention on OpenCode. Any other model (or `None`/empty) returns
   `None` immediately; no request is ever made for a non-Codex model.
3. **Read OAuth credentials.** Parses `_OPENCODE_AUTH_PATH` (OpenCode's own auth store — see
   [`_OPENCODE_AUTH_PATH`](#_opencode_auth_path) below) as JSON and looks up the `"openai"` entry.
   `token = creds["access"]`, `account = creds["accountId"]`. If `creds["type"] != "oauth"` or
   `token` is falsy (no OAuth session, or a different auth mode), returns `None` without a request.
4. **Send a minimal probe request** to `_CODEX_RESPONSES_URL`
   (`https://chatgpt.com/backend-api/codex/responses`) — a `POST` with the smallest possible body
   (a single `"ping"` user message, `store: False`) using the model name with its `"openai/"`
   prefix stripped. The point of the request is never its completion — when the subscription is
   capped it 429s **with the same `x-codex-*` reset headers attached** and bills nothing, so a
   minimal request is enough to read the headers either way.
5. **Read headers off whichever outcome occurred.** A success reads `resp.headers` then closes the
   response *without draining the body* (only the headers are wanted). An `HTTPError` (the capped
   429) reads `exc.headers` instead — Codex attaches the same `x-codex-*` headers to the error
   response.
6. **Extract and return.** `headers.get("x-codex-primary-reset-at")`; if present, `float(...)` it
   and return; otherwise `None`.
7. **Blanket exception guard.** Steps 3–6 run inside a `try`/`except Exception: return None` — a
   missing auth file, malformed JSON, network error, timeout, or unparsable header all collapse to
   the same `None`, never propagating to the caller.

### `_OPENCODE_AUTH_PATH`

- code: `workhorse/workhorse/runner/backends.py::_OPENCODE_AUTH_PATH`

Module-level `Path` constant: `$OPENCODE_AUTH_PATH` if set, else
`~/.local/share/opencode/auth.json` — OpenCode's own OAuth credential store, read directly so this
probe can authenticate as the same Codex session OpenCode itself uses.

### `_CODEX_RESPONSES_URL`

- code: `workhorse/workhorse/runner/backends.py::_CODEX_RESPONSES_URL`

Module-level `str` constant: `"https://chatgpt.com/backend-api/codex/responses"` — the Codex OAuth
backend's Responses-API endpoint this probe posts its minimal ping request to.

## Related pieces

- [`OpenCodeBackend.run_turn`](opencode-backend.md#contract) — the sole caller: invokes this only
  when [`_agent._is_cap(diagnostics)`](classify-turn.md) found the turn hit a usage cap, and passes
  the result through as `rate_reset_at` to [`_finalize_turn`](finalize-turn.md), which carries it
  onto the raised `BackendInvocationError.reset_at` (see [`_cap_delay_seconds`](cap-delay-seconds.md#algorithm),
  which prefers a structured `reset_at` over parsing reset text).
- [`_finalize_turn`](finalize-turn.md) — receives `rate_reset_at` from the caller and threads it
  onto the classified error.

