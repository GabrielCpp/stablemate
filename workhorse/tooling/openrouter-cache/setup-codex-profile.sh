#!/usr/bin/env bash
# Idempotently add a `mimo` codex profile that routes through the local LiteLLM
# proxy (so the xiaomi provider pin / caching applies). Codex 0.128+ speaks only
# the Responses API, and LiteLLM serves /v1/responses, so wire_api="responses".
#
#   ./setup-codex-profile.sh
#   CODEX_PROFILE=mimo AGENT_CLI=codex ./run-workflow.sh --workflow ...
set -euo pipefail

CONFIG="${CODEX_CONFIG:-$HOME/.codex/config.toml}"
PROXY="${LITELLM_BASE_URL:-http://localhost:4000}"
# Model the proxy forwards. With pin_proxy (forwards straight to OpenRouter) use
# the OpenRouter slug; with the LiteLLM proxy use its logical name (e.g. "mimo").
CODEX_MODEL="${CODEX_MODEL:-xiaomi/mimo-v2.5}"

mkdir -p "$(dirname "$CONFIG")"
touch "$CONFIG"

if grep -q '^\[profiles\.mimo\]' "$CONFIG"; then
  echo "✓ codex profile [profiles.mimo] already present in $CONFIG — leaving as-is."
  exit 0
fi

cat >> "$CONFIG" <<EOF

# ── Added by workhorse/tooling/openrouter-cache/setup-codex-profile.sh ────────
# MiMo-V2.5 via the local pin proxy on :4000 (xiaomi provider pin → cache reads).
# Auth value is a dummy (LITELLM_MASTER_KEY); the proxy injects the real key.
[model_providers.openrouter-cache]
name = "OpenRouter (xiaomi cache pin)"
base_url = "$PROXY/v1"
env_key = "LITELLM_MASTER_KEY"   # any non-empty value; the proxy injects real auth
wire_api = "responses"  # codex 0.128+ speaks only Responses; the proxy forwards it

[profiles.mimo]
model = "$CODEX_MODEL"
model_provider = "openrouter-cache"
model_reasoning_effort = "none"  # MiMo isn't a reasoning model; don't send effort
EOF

echo "✓ Added [profiles.mimo] + [model_providers.litellm-cache] to $CONFIG"
echo "  Run with: CODEX_PROFILE=mimo AGENT_CLI=codex ./run-workflow.sh --workflow ..."
