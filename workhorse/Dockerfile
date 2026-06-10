FROM ubuntu:24.04

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gosu \
    git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Claude CLI, then relocate the self-contained binary to a world-accessible
# path so the runtime `nobody` user can exec it (the installer drops it under
# root-only /root/.local).
RUN curl -fsSL https://claude.ai/install.sh | bash \
    && cp "$(readlink -f /root/.local/bin/claude)" /usr/local/bin/claude \
    && chmod a+rx /usr/local/bin/claude \
    && /usr/local/bin/claude --version

# Put the uv-managed Python in a world-readable location so nobody can use it at runtime
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python

WORKDIR /app

# Copy project files (pyproject.toml, uv.lock, workhorse package)
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY workhorse/ workhorse/

# Install Python deps — run as root during build, nobody at runtime
RUN uv sync --frozen \
    && chown -R nobody:nogroup /app \
    && chmod -R a+rX /opt/uv-python

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Mounts expected at runtime (see compose.yaml):
#   ~/.claude/.credentials.json → /mnt/claude-credentials.json:ro  Subscription auth (seeded once)
#   ~/.claude/settings.json     → /mnt/claude-settings.json:ro     Optional host Claude config
#   ./my-workflow               → /workflow                        Workflow dir (yaml+prompts+scripts)
#   workspace volume            → /workspace                       Agent clones/commits (persists)
#   claude-state volume         → /claude-state                    Sessions + seeded creds (persists)
#   runs volume                 → /runs                            Artifact output (persists)
#
# Auth (default): Claude subscription via the seeded ~/.claude/.credentials.json.
# Optional env:
#   CLAUDE_CODE_OAUTH_TOKEN  long-lived token from `claude setup-token` (skips the file seed)
#   WORKFLOW_PATH            path to workflow.yaml (default: /workflow/workflow.yaml)
#   AGENT_RUNS_DIR           artifact output dir  (compose sets /runs)
# Bedrock alternative: set CLAUDE_CODE_USE_BEDROCK=1 + AWS_PROFILE and mount ~/.aws (see compose.yaml).

ENTRYPOINT ["/entrypoint.sh"]
