# OpenRouter caching for MiMo-V2.5 (guaranteed)

Run workhorse workflows (`author`, `epic-coder`, …) on **MiMo-V2.5 via OpenRouter**
with prompt caching that actually fires — turning the ~$22/epic uncached worst
case into a few dollars.

## Why a proxy at all

Caching on OpenRouter is a property of how the request is *shaped*, not of the
model. MiMo-V2.5 has **two** providers on OpenRouter:

| Provider | Input | Output | Cache read |
|---|---|---|---|
| `xiaomi` | $0.14/M | $0.28/M | **$0.0028/M** (~98% off) |
| `digitalocean` | $0.14/M | $0.28/M | none |

If a request lands on `digitalocean`, or bounces between the two, the cache is
cold and you pay full input on every agentic turn. The fix is to **pin the
provider to `xiaomi` with fallbacks off** — then every turn of every node hits
the one caching provider and the prefix cache stays warm. `xiaomi` caches
*implicitly* (automatic), so no `cache_control` breakpoints or `session_id` are
needed; the pin is the whole guarantee.

No agent CLI (claude/codex/copilot) lets you set OpenRouter's `provider`
preference. A small proxy injects it for them — that's its only job.

```
agent CLI ──base URL──▶ pin proxy ──+ provider:{order:[xiaomi]}──▶ OpenRouter ▶ xiaomi
```

You have two proxies that do the identical injection — pick one:

| Proxy | Covers | Needs | When |
|---|---|---|---|
| **`pin_proxy.py`** (default) | codex, copilot | nothing (stdlib) | **recommended** — verified, no docker, self-records for stability checks |
| `compose.litellm.yaml` | claude, codex, copilot | docker | if you want the claude CLI, or a hardened gateway |

## Setup (codex — the default)

```bash
cp .env.example .env          # add OPENROUTER_API_KEY; LITELLM_MASTER_KEY can be any string
python3 verify_cache.py        # optional: prove caching at the source ("✅ CONFIRMED")

# 1. start the pin proxy on :4000 (records every request to runs/capture/)
OPENROUTER_API_KEY=$OPENROUTER_API_KEY python3 pin_proxy.py serve &
# 2. add the codex `mimo` profile (points at the proxy, Responses API)
./setup-codex-profile.sh
```

> Using the LiteLLM proxy instead? `docker compose -f compose.litellm.yaml up -d`
> and set `CODEX_MODEL=mimo` before `setup-codex-profile.sh` (LiteLLM's logical
> name). Note: codex-via-LiteLLM relies on LiteLLM's Responses bridge, which is
> untested here — the verified codex path is `pin_proxy.py`.

## Run a workflow

```bash
./run-workflow.sh --workflow /path/to/agents/workflows/author/workflow.yaml
```

`run-workflow.sh` reads `.env`, wires the chosen CLI to the proxy, and execs
`workhorse` with your args. Override per run with `AGENT_CLI=copilot` or
`AGENT_MODEL=mimo-pro`.

## Which CLI

The proxy guarantees the **OpenRouter-side** caching. Whether a CLI *benefits*
also depends on it keeping a **stable, append-only prefix** across turns. All
three were checked; **codex and copilot are verified end-to-end** with live runs.

| CLI | Talks to proxy via | Prefix stability | Verdict |
|---|---|---|---|
| **codex** | `~/.codex` profile → `/v1/responses` | **verified append-only** | ✅ **default** — ~99% cached |
| **copilot** | `COPILOT_PROVIDER_BASE_URL` → `/v1` (BYOK) | **verified append-only** | ✅ confirmed — ~99% cached |
| claude | `ANTHROPIC_BASE_URL` → `/v1/messages` | stable by design (native cache_control) | ✅ works; needs the LiteLLM proxy |

`run-workflow.sh` sets the right env vars for whichever `AGENT_CLI` you pick.

### Codex — verified (the default)

Codex 0.128+ speaks **only** the Responses API (`chat` broke Feb 2026). It can't
set the `provider` pin itself, so it goes through the proxy, which forwards to
OpenRouter's `/responses` endpoint. A live two-turn tool run:

```
turn 1  input=[3 items]  prompt=10640  cached=10624   (99.8%)
turn 2  input=[6 items]  prompt=10721  cached=10624   ← only +81 tool-output tokens uncached
```

Codex sends `store=false` with no `previous_response_id`, so it resends the full
**append-only** input each turn — turn 2 kept turn 1's 3 items byte-identical and
appended the tool exchange. The `xiaomi` cache covers ~99% of every turn.
`setup-codex-profile.sh` writes the profile; `pin_proxy.py` is the proxy.

### Copilot — verified

Copilot CLI BYOK (≥ 2026-04-07) is configured by env vars that `run-workflow.sh`
sets: `COPILOT_PROVIDER_BASE_URL`, `COPILOT_PROVIDER_API_KEY`, `COPILOT_MODEL`,
`COPILOT_OFFLINE=true`. Live two-turn run:

```
turn 1 [system,user]            prompt=13210  cached=0       (cache write)
turn 2 [system,user,asst,tool]  prompt=13278  cached=13184   ← 99.3% from cache
```

Append-only prefix; ~33× cost drop on turn 2 ($0.00186 → $0.000056). Copilot
honors the custom endpoint **and** keeps a stable prefix.

### Claude

Claude emits Anthropic-native `cache_control` and keeps a stable prefix, but
speaks `/v1/messages` — which only the LiteLLM proxy translates (pin_proxy is
OpenAI/Responses only). Use it via `docker compose -f compose.litellm.yaml up -d`
and `AGENT_CLI=claude`.

## Confirming caching during a real run

- **Mechanics only (no CLI):** `python3 verify_cache.py` — two identical requests
  straight to OpenRouter; expects `cached_tokens > 0` on call #2.
- **A specific CLI, end-to-end:** point it at `pin_proxy.py` and inspect:
  ```bash
  OPENROUTER_API_KEY=$OPENROUTER_API_KEY python3 pin_proxy.py serve --port 4100 --dir runs/cap &
  # run the CLI with its base URL = http://127.0.0.1:4100/v1 on a tool-using task
  python3 pin_proxy.py analyze runs/cap     # append-only? cached tokens per turn?
  ```
- **During a workflow:** watch the LiteLLM proxy logs for non-zero `cached_tokens`,
  or OpenRouter dashboard → Activity (cached requests show the discounted cost).

## Files

| File | Purpose |
|---|---|
| `litellm-config.yaml` | Proxy model defs + the `xiaomi` provider pin (the guarantee) |
| `compose.litellm.yaml` | Runs the proxy on `:4000` |
| `.env.example` | Keys + run defaults (copy to `.env`, gitignored) |
| `run-workflow.sh` | Sets per-CLI env (claude/codex/copilot), execs `workhorse` |
| `setup-codex-profile.sh` | Idempotently adds the `mimo` codex profile (Responses API) |
| `verify_cache.py` | Proves caching fires upstream (identical requests → `cached_tokens`) |
| `pin_proxy.py` | Diagnostic proxy: records requests + pins `xiaomi`; checks client prefix stability |
