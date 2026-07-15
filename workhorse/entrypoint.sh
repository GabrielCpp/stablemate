#!/bin/bash
set -euo pipefail

# /claude-state is a named Docker volume mounted at runtime. It persists Claude
# session history, the seeded subscription credentials, and the onboarding flag
# across container restarts and reboots. HOME points here so the Claude CLI finds
# ~/.claude there.
CLAUDE_HOME=/claude-state
export HOME="$CLAUDE_HOME"

require_writable_dir() {
    local path="$1"
    if [ ! -d "$path" ] || [ ! -w "$path" ]; then
        echo "[entrypoint] ERROR: $path must be writable by $(id -un):$(id -gn)." >&2
        echo "[entrypoint] Prepare the named volume ownership before starting this non-root container." >&2
        exit 13
    fi
}

# The image and compose file run as nobody from process start.
# Volume ownership must be prepared before launch; this container never repairs it
# as root. The image pre-creates these mountpoints with nobody ownership so
# fresh named volumes can inherit the intended owner, and existing volumes can be
# fixed manually with chown when needed.
require_writable_dir /workspace
require_writable_dir /runs
require_writable_dir "$CLAUDE_HOME"

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

# Git identity for commits made inside the container (branch/commit/PR workflow
# steps). `nobody`'s UID may not match a bind-mounted host clone owner, so safe.directory is
# required regardless of where checkout happens — must run before any clone/
# checkout step touches a repo. Overridable per product via GIT_AUTHOR_EMAIL/
# GIT_AUTHOR_NAME (farrier can forward these through envPassthrough, same as
# ACME_GITHUB_TOKEN).
git config --global --add safe.directory '*'
git config --global user.email "${GIT_AUTHOR_EMAIL:-agent@acme.local}"
git config --global user.name "${GIT_AUTHOR_NAME:-Acme Agent}"

# A workflow may own checkout preparation (for example, resolving its configured
# credential before cloning a private remote). Otherwise use Workhorse's generic,
# unauthenticated checkout. The hook convention is generic; provider/token policy
# stays entirely in the workflow.
if [ -f /workflow/scripts/checkout-workspace.py ]; then
    uv run python3 /workflow/scripts/checkout-workspace.py
else
    uv run python3 -c \
        "from workhorse.scriptutil import checkout_workspace; checkout_workspace()"
fi

# Launch the groom-sidecar session in the background, ahead of the main run
# command below. It only ever observes /workspace + /runs and holds a WebSocket
# to a host-side `groom` dashboard (if one is listening); it never affects this
# script's own exit code. stdout/stderr are discarded so a noisy or crashing
# sidecar never interleaves with or pollutes the workflow's own logs.
#
# Editable sidecar (the `pipx install --editable` model). groom is not baked into
# the image; it is installed as an editable uv *tool* from a bind of the host
# groom/ source at /mnt/groom-src (read-only; see compose.yaml). `--editable`
# points the install at the live bind, so an edit on the host is imported by the
# next sidecar start — a `reload` (or `docker restart`) is all it takes, no image
# rebuild. `--no-sources` installs standalone (ignoring the uv workspace source
# groom declares for workhorse-agent), pulling workhorse-agent + groom's deps
# from PyPI into an isolated tool venv under HOME=/claude-state — persistent, so
# only a fresh volume's first start pays a download. Running straight off the
# read-only bind is fine: it is world-readable, PYTHONDONTWRITEBYTECODE stops
# .pyc writes, and a manual reload happens after a save (no partial files). With
# no bind, nothing is installed and the container runs without a sidecar.
GROOM_TOOL_BIN="$CLAUDE_HOME/.local/bin"
GROOM_SIDECAR="$GROOM_TOOL_BIN/groom-sidecar"
if [ -d /mnt/groom-src ]; then
    UV_TOOL_BIN_DIR="$GROOM_TOOL_BIN" uv tool install --editable /mnt/groom-src --no-sources >/dev/null 2>&1 || true
fi

# Supervised reload owned by this shell (PID 1): the sidecar signals a reload by
# exiting with code 3 (groom sends `reload` over the socket it holds) and the
# loop simply restarts it — the editable install imports the live bind source,
# so no copy or reinstall is needed. Any other exit stops the loop, so a reload
# that lands on unimportable code fails safe (no restart storm); a
# `docker restart` reruns this entrypoint. No installed sidecar (no bind, or a
# failed install) → the loop returns immediately and the workflow runs without one.
run_sidecar() {
    [ -x "$GROOM_SIDECAR" ] || return 0
    while :; do
        PYTHONDONTWRITEBYTECODE=1 "$GROOM_SIDECAR" >/dev/null 2>&1 && rc=0 || rc=$?
        [ "$rc" = 3 ] || break
    done
}
run_sidecar &

# Run workhorse in the background (not `exec`) so this shell survives its exit
# and can fire a one-shot "workflow exited" push to groom. The container tears
# down the moment PID 1 dies, SIGKILLing the sidecar, so the sidecar itself
# can't reliably report the exit — the entrypoint has to, while still alive.
# Point HOME at the volume so Claude CLI finds ~/.claude there.
# CLAUDE_CODE_OAUTH_TOKEN (if set) is inherited from the environment.
uv run workhorse \
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
# never change the container's own exit status. Skipped when no sidecar was
# installed (no groom bind); `|| true` keeps any failure off the exit code.
[ -x "$GROOM_SIDECAR" ] && "$GROOM_SIDECAR" --exit-code "$rc" >/dev/null 2>&1 || true

exit "$rc"
