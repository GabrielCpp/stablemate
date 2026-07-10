---
type: feature
slug: sidecar-autostart
title: Sidecar autostart — launched by the container entrypoint
status: implemented
id: stablemate-5
area: groom
---
# Sidecar autostart — launched by the container entrypoint

`groom-sidecar` starts **automatically** inside every workflow container — there
is no operator step. When a container is brought up through the
farrier-generated Makefile, the sidecar is already running and pushing to a
host-side groom (if one is listening).

## Behaviour

- The container entrypoint launches the watcher in the background ahead of the
  workflow run. It is now wrapped in a **supervising loop** (`run_sidecar`)
  rather than a bare `&`, so a sidecar that exits with code 3 (a `reload`
  request over its socket) is relaunched; any other exit stops the loop. groom is
  installed as an editable uv tool from a read-only `../groom:/mnt/groom-src`
  bind, so the relaunch imports the edited host source with no image rebuild. See
  [sidecar-live-sessions](sidecar-live-sessions.md) for the reload contract.
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
- `groom-sidecar` is **not** baked into the agent image. It is installed at
  container start as an editable uv **tool** (`uv tool install --editable
  /mnt/groom-src --no-sources`) from a read-only bind of the host `groom/`
  source — the `pipx install --editable` model. `--no-sources` installs it
  standalone (pulling `workhorse-agent` + deps from PyPI, cached on the
  `claude-state` volume) since groom's `tool.uv.sources` workspace entry only
  binds `uv`'s workspace-aware resolvers, not `pip`/`--no-sources`. Because it is
  editable off the live bind, a `reload` (or `docker restart`) just restarts it
  and imports the edit — no copy, no reinstall, no image rebuild (see
  [sidecar-live-sessions](sidecar-live-sessions.md)). Without the bind, no
  sidecar is installed and the workflow runs without one — never fatal.

## Implementation

- `workhorse/entrypoint.sh` — `uv tool install --editable` from the bind, then
  the `run_sidecar` supervising loop (restart on exit 3), `trap` for signal
  forwarding, post-run `groom-sidecar --exit-code`.
- `workhorse/Dockerfile` — bakes workhorse + ostler; groom is the editable tool
  installed at runtime from the bind, not baked.
- `workhorse/compose.yaml` + farrier's generated `.agents/local.compose.yaml` —
  `extra_hosts: host.docker.internal:host-gateway` so the sidecar can reach a
  bridge-bound groom (see [sidecar-protocol](sidecar-protocol.md)).

## Related

- [sidecar-protocol](sidecar-protocol.md)
