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

# Git identity for commits made inside the container (branch/commit/PR workflow
# steps). `nobody`'s UID won't match the host clone owner, so safe.directory is
# required regardless of where checkout happens — must run before any clone/
# checkout step touches a repo. Overridable per product via GIT_AUTHOR_EMAIL/
# GIT_AUTHOR_NAME (farrier can forward these through envPassthrough, same as
# PREDYKT_GITHUB_TOKEN).
gosu nobody env HOME="$CLAUDE_HOME" git config --global --add safe.directory '*'
gosu nobody env HOME="$CLAUDE_HOME" git config --global user.email "${GIT_AUTHOR_EMAIL:-agent@predykt.local}"
gosu nobody env HOME="$CLAUDE_HOME" git config --global user.name "${GIT_AUTHOR_NAME:-Predykt Agent}"

# Clone/update every folder listed in the .code-workspace file (or the single
# REPO_URL/REPO_NAME/REPO_BRANCH fallback repo) into /workspace, transparent to
# whichever workflow graph runs next — neither coder nor author has a "setup" node.
gosu nobody env HOME="$CLAUDE_HOME" uv run python3 -c \
    "from workhorse.scriptutil import checkout_workspace; checkout_workspace()"

# Launch the groom-sidecar watcher in the background, ahead of the main run
# command below. It only ever observes /workspace + /runs and pushes
# fire-and-forget updates to a host-side `groom` dashboard (if one is
# listening); it never affects this script's own exit code. stdout/stderr are
# discarded so a noisy or crashing sidecar never interleaves with or pollutes
# the workflow's own logs.
gosu nobody env HOME="$CLAUDE_HOME" uv run groom-sidecar >/dev/null 2>&1 &

# Run workhorse in the background (not `exec`) so this shell survives its exit
# and can fire a one-shot "workflow exited" push to groom. The container tears
# down the moment PID 1 dies, SIGKILLing the sidecar, so the sidecar itself
# can't reliably report the exit — the entrypoint has to, while still alive.
# Point HOME at the volume so Claude CLI finds ~/.claude there.
# CLAUDE_CODE_OAUTH_TOKEN (if set) is inherited from the environment.
gosu nobody env HOME="$CLAUDE_HOME" uv run workhorse \
    --workflow "${WORKFLOW_PATH:-/workflow/workflow.yaml}" \
    ${AGENT_RUNS_DIR:+--runs-dir "$AGENT_RUNS_DIR"} \
    "$@" &
wf_pid=$!

# Forward docker stop's SIGTERM/SIGINT to the workflow so shutdown stays
# graceful now that this shell (not workhorse) is PID 1.
trap 'kill -TERM "$wf_pid" 2>/dev/null' TERM INT

# `set -e` would abort on a non-zero workflow exit before we could notify, so
# capture the code explicitly.
rc=0
wait "$wf_pid" || rc=$?

# Best-effort exit notice (reuses the sidecar's identity/host/port logic); must
# never change the container's own exit status.
gosu nobody env HOME="$CLAUDE_HOME" uv run groom-sidecar --exit-code "$rc" >/dev/null 2>&1 || true

exit "$rc"
