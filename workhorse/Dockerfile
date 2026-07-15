FROM ubuntu:24.04

# Install system deps, plus the gh and docker apt repos (both ship only a signing
# key + repo file via apt, not a direct package — added before the single
# apt-get install below so gh/docker packages resolve in the same layer).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    git \
    openssh-client \
    python3 \
    python3-pip \
    python3-venv \
    unzip \
    xz-utils \
    && mkdir -p -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list \
    && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get update && apt-get install -y --no-install-recommends \
    gh \
    docker-ce-cli \
    docker-compose-plugin \
    nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && gh --version && docker --version && docker compose version && node --version && python3 --version

# Install Bun, then relocate the binary to a world-accessible path (nobody runs
# at runtime) — same relocation pattern as the Claude CLI below.
RUN curl -fsSL https://bun.sh/install | bash \
    && cp /root/.bun/bin/bun /usr/local/bin/bun \
    && chmod a+rx /usr/local/bin/bun \
    && /usr/local/bin/bun --version

# Install Go (official tarball) into a world-readable location.
ARG GO_VERSION=1.23.4
RUN curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" -o /tmp/go.tar.gz \
    && tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm /tmp/go.tar.gz \
    && chmod -R a+rX /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}"
RUN go version

# Install Flutter (official stable-channel tarball) into a world-readable
# location; precache the SDK's own tooling at build time so the first run
# doesn't pay that cost. Heaviest layer in the image — built once and reused.
ARG FLUTTER_VERSION=3.27.1
RUN curl -fsSL "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz" -o /tmp/flutter.tar.xz \
    && tar -C /opt -xJf /tmp/flutter.tar.xz \
    && rm /tmp/flutter.tar.xz \
    && chmod -R a+rX /opt/flutter
ENV PATH="/opt/flutter/bin:${PATH}"
RUN git config --global --add safe.directory /opt/flutter \
    && flutter precache \
    && flutter --version \
    && chmod -R a+rX /opt/flutter

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

# Copy project files (pyproject.toml, uv.lock, workhorse + ostler packages).
# groom is NOT baked here: the in-container groom-sidecar is installed at
# container start as an editable uv *tool* (the `pipx install --editable` model)
# from a bind of the host groom/ source — see entrypoint.sh. `uv tool install
# --editable … --no-sources` installs it standalone, pulling workhorse-agent +
# groom's deps from PyPI (cached on the persistent claude-state volume) rather
# than resolving this uv workspace, so groom needs no workspace-member source in
# the image and an edit reaches the sidecar with no image rebuild. A container
# with no groom bind just runs without a sidecar.
# ostler, by contrast, must be baked in globally: workflow script nodes
# (validate-artifacts.py, verify-surface-coverage.py, reconcile-artifacts.py,
# ostler-doctor.py) shell out to `ostler` directly as workhorse subprocesses,
# not through an agent's own shell — an agent ad hoc `uv tool install ostler`-ing
# itself mid-run does not make the binary visible to those sibling script processes.
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY workhorse/ workhorse/
COPY ostler/ ostler/

# Install Python deps — run as root during build, nobody at runtime. groom is
# omitted (installed at runtime as an editable tool from the bind); workhorse +
# ostler are baked so the workflow runs offline. A missing groom/ workspace
# member is tolerated by `uv sync` (farrier is likewise never copied).
RUN uv sync --frozen --package workhorse-agent --package ostler \
    && ln -sf /app/.venv/bin/ostler /usr/local/bin/ostler \
    && chown -R nobody:nogroup /app \
    && mkdir -p /workspace /runs /claude-state \
    && chown -R nobody:nogroup /workspace /runs /claude-state \
    && mkdir -p /opt/uv-python \
    && chmod -R a+rX /opt/uv-python

COPY workhorse/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER nobody
ENV HOME=/claude-state

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
