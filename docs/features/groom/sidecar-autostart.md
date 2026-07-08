---
type: feature
id: stablemate-5
slug: sidecar-autostart
title: Sidecar autostart — launched by the container entrypoint
area: groom
status: implemented
---
# Sidecar autostart — launched by the container entrypoint

`groom-sidecar` starts **automatically** inside every workflow container — there
is no operator step. When a container is brought up through the
farrier-generated Makefile, the sidecar is already running and pushing to a
host-side groom (if one is listening).

## Behaviour

- The container entrypoint launches the watcher in the background ahead of the
  workflow run: `gosu nobody env HOME=/claude-state uv run groom-sidecar &`.
- Because the entrypoint (not workhorse) is PID 1, it forwards `SIGTERM` to the
  workflow and, after the run returns, fires a one-shot
  `groom-sidecar --exit-code "$rc"` so groom learns the workflow finished (the
  container tears down before the inotify loop could report it).
- Entry point: the farrier-generated `.agents/agents.mk` — `make agent-run` /
  `make agent-build` (WF=author|coder) runs `docker compose up`, whose service
  uses `workhorse`'s image + `entrypoint.sh`.

## Invariants (load-bearing)

- The sidecar never affects the container's own exit code or behaviour; its
  stdout/stderr are discarded so it can't pollute the workflow log.
- `groom-sidecar` is baked into the agent image at build time
  (`workhorse/Dockerfile`: `COPY groom/` + `uv sync … --package groom`). **A
  sidecar code change only reaches a container after the image is rebuilt**
  (`make agent-build`) — running an old image gives a stale sidecar (e.g. one
  that predates `--query`). This is the single most common gotcha.

## Implementation

- `workhorse/entrypoint.sh` — background `groom-sidecar &`, `trap` for signal
  forwarding, post-run `groom-sidecar --exit-code`.
- `workhorse/Dockerfile` — bakes `groom` into the image.
- `workhorse/compose.yaml` + farrier's generated `.agents/local.compose.yaml` —
  `extra_hosts: host.docker.internal:host-gateway` so the sidecar can reach a
  bridge-bound groom (see [sidecar-protocol](sidecar-protocol.md)).

## Related

- [sidecar-protocol](sidecar-protocol.md) · architecture overview:
  [../groom.md](../groom.md)
