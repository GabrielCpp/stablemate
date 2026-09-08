---
type: environment
slug: workhorse-container
title: workhorse container environment
---
# workhorse container environment

- selector: the Compose project created for a workhorse agent launch
- services:
  - agent: no network listener; the one-shot workflow container runs from the Compose project
- backing:
  - workspace: named volume mounted at `/workspace` for clone-mode checkouts
  - claude-state: named volume mounted at `/claude-state` for Claude sessions, onboarding state, and seeded credentials
  - runs: named volume mounted at `/runs` for prompts, outputs, context snapshots, and run records
- local-only: true
- code: `workhorse/compose.yaml`
- code: `workhorse/Dockerfile`
- detail: [container supervisor](../concepts/container-supervisor.md)
- verify: exit_status(code=0)

This environment is the local Docker harness for isolated, unattended workflow runs. Compose
builds the `agent` service with `context: ..` from the repository root and
`dockerfile: workhorse/Dockerfile`; the image includes the engine and installed workflow
distributions, while the optional groom source is mounted read-only and installed by the
supervisor at startup.

The service runs as `${AGENT_UID:-65534}:${AGENT_GID:-65534}` with Docker's init process. Its
required runtime inputs are the read-only credentials seed at `/mnt/claude-credentials.json`,
the optional same-path repository bind used by worktree mode, and the optional same-path staged
agent config bind. `WORKFLOW`, `AGENT_RUN_ID`, source/check-out variables, model profile variables,
telemetry variables, and groom connection variables are passed through the Compose environment;
unset values use the defaults declared by `compose.yaml`.

The three named volumes are isolated by the Compose project name and survive container restarts.
`workspace` holds clone-mode working trees, `claude-state` is the container `HOME` and retains
rotated credentials and sessions, and `runs` retains workflow artifacts. A fresh launch gets a new
project and run id; `docker restart` re-enters the same container and resumes that run. This
environment is local-only because it requires Docker, host credential input, and host filesystem
binds, and its default groom endpoint assumes `host.docker.internal:8787`.
