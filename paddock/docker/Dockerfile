FROM python:3.12.13-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

ARG CLAUDE_CODE_VERSION
ARG OPENCODE_VERSION
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" "opencode-ai@${OPENCODE_VERSION}" \
    && npm cache clean --force

COPY wheels /tmp/wheels
RUN python3 -m pip install --no-cache-dir \
        /tmp/wheels/workhorse_workflows-*.whl /tmp/wheels/workhorse_agent-*.whl \
        /tmp/wheels/ostler-*.whl /tmp/wheels/farrier-*.whl \
    && rm -rf /tmp/wheels /root/.cache

RUN git config --system user.name "paddock sandbox" \
    && git config --system user.email sandbox@example.com \
    && git config --system --add safe.directory "*"

ENV HOME=/tmp/sandbox-home
ENV PYTHONDONTWRITEBYTECODE=1
RUN mkdir -p /tmp/sandbox-home/.claude /tmp/sandbox-home/.agents /tmp/sandbox-home/.local/share/opencode && chmod -R 0777 /tmp/sandbox-home

WORKDIR /work
