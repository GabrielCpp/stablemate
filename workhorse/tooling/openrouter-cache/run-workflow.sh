#!/usr/bin/env bash
# Run a workhorse workflow with the active agent CLI pointed at the local
# LiteLLM proxy, so every request is pinned to OpenRouter's caching `xiaomi`
# provider for MiMo-V2.5.
#
# Usage:
#   ./run-workflow.sh --workflow /path/to/workflow.yaml [more workhorse args...]
#   AGENT_CLI=codex ./run-workflow.sh --workflow ...      # override CLI
#
# Prereq: the proxy is up (docker compose -f compose.litellm.yaml up -d).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$HERE/.env" ]; then set -a; . "$HERE/.env"; set +a; fi

PROXY="${LITELLM_BASE_URL:-http://localhost:4000}"
KEY="${LITELLM_MASTER_KEY:?set LITELLM_MASTER_KEY in .env}"
CLI="${AGENT_CLI:-codex}"
MODEL="${AGENT_MODEL:-mimo}"

case "$CLI" in
  claude)
    # Claude CLI calls <base>/v1/messages (Anthropic format); LiteLLM serves it.
    export ANTHROPIC_BASE_URL="$PROXY"
    export ANTHROPIC_API_KEY="$KEY"
    ;;
  codex)
    # Codex 0.128+ speaks ONLY the Responses API; it reads provider+model from a
    # ~/.codex/config.toml profile (run ./setup-codex-profile.sh once). The
    # profile points at the proxy's /v1 (wire_api="responses") so the xiaomi pin
    # still applies. LITELLM_MASTER_KEY is the profile's env_key.
    export CODEX_PROFILE="${CODEX_PROFILE:-mimo}"
    export LITELLM_MASTER_KEY="$KEY"
    ;;
  copilot)
    # Copilot CLI BYOK (>= 2026-04-07): point it at an OpenAI-compatible endpoint
    # via COPILOT_PROVIDER_* envs. We route through the proxy so the xiaomi pin
    # applies. COPILOT_MODEL is the proxy's logical name ("mimo").
    export COPILOT_PROVIDER_BASE_URL="$PROXY/v1"
    export COPILOT_PROVIDER_API_KEY="$KEY"
    export COPILOT_MODEL="$MODEL"
    # Don't let it phone GitHub for model routing; talk only to our provider.
    export COPILOT_OFFLINE="${COPILOT_OFFLINE:-true}"
    ;;
  *)
    echo "unknown AGENT_CLI=$CLI (want claude|codex|copilot)" >&2; exit 2 ;;
esac

export AGENT_CLI="$CLI"
export AGENT_MODEL="$MODEL"

echo "→ CLI=$CLI  model=$MODEL  proxy=$PROXY" >&2
exec workhorse "$@"
