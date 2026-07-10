---
type: feature
slug: sidecar-protocol
title: Sidecar protocol — two-way groom to container channel
status: implemented
id: stablemate-4
area: groom
---
# Sidecar protocol — two-way groom to container channel

groom and each workflow container talk to each other through the in-container
`groom-sidecar`. The channel is **bidirectional**: the container pushes events
up to groom, and groom queries the container's sidecar back down.

> **Superseded as the primary channel.** The steady-state channel is now the
> persistent WebSocket session in
> [sidecar-live-sessions](sidecar-live-sessions.md): the sidecar advertises
> full state on connect and streams `progress`/`blocked` over the socket, and
> groom serves the Files/Diff panels via `getTree`/`getFile`/`getDiff` RPC over
> the same socket instead of `docker exec … --query` + throwaway volume reads.
> What remains of the HTTP path below is **residual best-effort**: the one-shot
> `exited` notice the entrypoint fires after workhorse returns, and the
> `await_operator.py` backstop POST to `/push/blocked`. The `--query` snapshot
> is still the sidecar's `hello` payload, and the volume reads are still the
> fallback for a container with no live sidecar.

## Container → host (fire-and-forget push)

- `groom-sidecar` watches `/workspace` + `/runs` with `inotify` and POSTs
  `progress` / `blocked` events to the host groom at
  `http://host.docker.internal:8787/push/*`. A one-shot `exited` push is fired
  by the entrypoint after the workflow returns.
- Every push is best-effort: a short (1.0s) timeout wrapped in a broad
  `except: pass`. It never retries and never raises — a container with no groom
  listening behaves exactly as it would without groom.
- The `await_operator.py` wait script fires the same `blocked` push as an
  idempotent backstop when it shows a gate banner.

## Host → container (sidecar query)

- For a **running** container, groom asks its sidecar for a one-shot snapshot:
  `docker exec -u nobody -e HOME=/claude-state <cid> uv run groom-sidecar --query`
  prints `{current_node, terminal, gates:[{file_path, question}]}` as JSON
  (`sidecar.snapshot()` — pure file reads, no network, no inotify).
- Discovery prefers this fast path for running containers and falls back to
  reading the named volumes via throwaway containers for stopped/legacy ones.

## Invariants (load-bearing)

- **Fire-and-forget discipline** on every push site: short timeout, silent on
  failure, never blocks or changes the workflow's exit code. Preserve this in any
  new push.
- **Linux networking gotcha:** the compose `host-gateway` maps to the docker
  bridge, not the host loopback. groom must therefore bind a bridge-reachable
  address, which is why `groom serve` now **defaults to `0.0.0.0`** (a
  `127.0.0.1`-only bind silently drops every push/socket from a container).
  It warns on the non-loopback bind since groom has no auth; `--host 127.0.0.1`
  restores loopback-only.
- The `--query` snapshot is a bounded, safe one-shot `docker exec`; it walks
  `/workspace` skipping vendor dirs (`.git`, `.venv`, `node_modules`,
  `__pycache__`).

## Network path

`farrier`'s generated compose adds
`extra_hosts: ["host.docker.internal:host-gateway"]` to every workflow service,
so a container can always reach a bridge-bound groom on the host — no per-repo
change needed.

## Implementation

- `groom/groom/sidecar.py` — `push_progress`/`push_blocked`/`push_exited`,
  `snapshot`/`scan_gates`, the `run()` inotify loop.
- `groom/groom/cli.py::sidecar_main` — `--query` / `--exit-code`.
- `groom/groom/app.py` — `POST /push/{progress,blocked,exited}`.
- `groom/groom/docker_io.py::sidecar_query`, `docker_exec`.
- `groom/groom/discovery.py::_resolve_container`, `_apply_snapshot`.
- Tests: `groom/tests/test_sidecar.py`, `groom/tests/test_docker_io.py`,
  `groom/tests/test_discovery.py`.

## Related

- [sidecar-autostart](sidecar-autostart.md) · [operator-inbox](operator-inbox.md)
