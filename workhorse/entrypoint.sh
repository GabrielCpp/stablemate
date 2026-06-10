#!/bin/bash
set -euo pipefail

# /claude-state is a named Docker volume mounted at runtime. It persists Claude
# session history, the seeded subscription credentials, and the onboarding flag
# across container restarts and reboots. HOME points here so the Claude CLI finds
# ~/.claude there.
CLAUDE_HOME=/claude-state
mkdir -p "$CLAUDE_HOME/.claude"

# Optional Claude config (settings.json) — config, not a secret, so refresh each
# start if the host provides it.
if [ -f /mnt/claude-settings.json ]; then
    cp /mnt/claude-settings.json "$CLAUDE_HOME/.claude/settings.json"
fi

# Auth. Priority: an explicit OAuth token wins; otherwise seed the subscription
# credentials file ONCE into the persistent volume. We must not overwrite a
# token the CLI has since refreshed/rotated in-volume with a stale host copy —
# so only seed when the volume has no credentials yet. To re-seed (e.g. after
# re-authenticating on the host), clear the claude-state volume
# (`make research-reseed-auth`).
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    echo "[entrypoint] auth: using CLAUDE_CODE_OAUTH_TOKEN" >&2
elif [ -f "$CLAUDE_HOME/.claude/.credentials.json" ]; then
    echo "[entrypoint] auth: using credentials already in claude-state volume" >&2
elif [ -f /mnt/claude-credentials.json ]; then
    echo "[entrypoint] auth: seeding subscription credentials into claude-state volume" >&2
    cp /mnt/claude-credentials.json "$CLAUDE_HOME/.claude/.credentials.json"
    chmod 600 "$CLAUDE_HOME/.claude/.credentials.json"
else
    echo "[entrypoint] WARNING: no CLAUDE_CODE_OAUTH_TOKEN and no credentials mounted at" \
         "/mnt/claude-credentials.json — Claude CLI will not be authenticated." >&2
fi

# Skip the interactive onboarding flow in headless mode. A minimal stub is enough;
# the OAuth account is resolved from the token/credentials.
if [ ! -f "$CLAUDE_HOME/.claude.json" ]; then
    echo '{"hasCompletedOnboarding": true}' > "$CLAUDE_HOME/.claude.json"
fi

chown -R nobody:nogroup "$CLAUDE_HOME"

# The /workspace (agent clones) and /runs (artifacts) named volumes are root-owned
# at creation. The controller runs as `nobody`, so hand it the mount roots; their
# contents are then created by nobody. Non-recursive keeps re-runs fast (the clone
# + venv under /workspace can be large).
mkdir -p /workspace /runs
chown nobody:nogroup /workspace /runs

# Point HOME at the volume so Claude CLI finds ~/.claude there. CLAUDE_CODE_OAUTH_TOKEN
# (if set) is inherited from the environment.
exec gosu nobody env HOME="$CLAUDE_HOME" uv run workhorse \
    --workflow "${WORKFLOW_PATH:-/workflow/workflow.yaml}" \
    ${AGENT_RUNS_DIR:+--runs-dir "$AGENT_RUNS_DIR"} \
    "$@"
