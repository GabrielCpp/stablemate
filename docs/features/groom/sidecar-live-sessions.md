---
type: feature
slug: sidecar-live-sessions
title: Sidecar live sessions — persistent socket data plane + dev reload
status: proposed
id: stablemate-6
area: groom
---
# Sidecar live sessions — persistent socket data plane + dev reload

**Status: proposed.** This is a design direction, not shipped behaviour. It
evolves the current best-effort push/pull channel (see
[sidecar-protocol](sidecar-protocol.md)) into a persistent, stateful session and
uses that session as the data plane for groom's interactive panels. It also
specifies the local development loop for iterating on the sidecar without an
image rebuild.

## Motivation

groom's Files and Diff panels need fast, per-container reads: the file tree of a
checkout, a single file's contents, and a repo's working-tree diff. Today every
such read spawns a **throwaway container** — `docker run alpine find` /
`docker run alpine/git diff` / `docker run alpine cat` against the workflow's
`/workspace` volume (`groom.docker_io`). That path is uniform and works for
stopped containers, but each request pays container-create + image + mount
latency (hundreds of ms), and it can never stream live changes.

The sidecar already has what those reads want: the workspace on **local disk**
plus an `inotify` loop. Promoting it from a fire-and-forget *signal* to a
persistent *session* lets it serve those reads from memory and stream deltas,
and collapses several host-side mechanisms (liveness polling, state
reconstruction) into one connection.

## Baseline today (what this replaces)

- **Discovery** is a one-shot `docker ps -a` + `docker inspect` scan
  (`groom.discovery`). A container is a workflow iff it mounts `/workflow`,
  `/runs`, and `/workspace`; the workflow *kind* is the basename of the
  `/workflow` mount source. Steady state comes from sidecar pushes, not a timer.
- **Channel** is best-effort and two-way (see [sidecar-protocol](sidecar-protocol.md)):
  the container POSTs `progress`/`blocked`/`exited` to
  `http://host.docker.internal:8787/push/*`; groom pulls a snapshot for a running
  container with `docker exec … groom-sidecar --query`; stopped/legacy containers
  fall back to volume reads.
- **Interactive data plane** (Files/Diff) is the throwaway-container volume-read
  path described above.
- The sidecar is **baked into the image** at build time (see
  [sidecar-autostart](sidecar-autostart.md)): `workhorse/Dockerfile` `COPY groom/`
  + `uv sync … --package groom`, launched by `entrypoint.sh` as
  `gosu nobody env HOME=/claude-state uv run groom-sidecar &`.

## Design principle

**Push for latency, pull for correctness — and make the push reliable enough to
own correctness for connected containers.** A single lost fire-and-forget packet
today can strand a workflow (a gate never surfaced), which is why the poll had to
be authoritative. A persistent socket with **re-advertise-full-state-on-connect**
closes that gap: the session becomes authoritative for connected containers, and
the reconcile scan demotes to cold-start discovery.

The sidecar stays **non-authoritative and its state ephemeral**: everything
re-syncs on (re)connect. That single property is what makes every restart below —
sidecar reload, host groom restart, container recreate — safe and cheap.

## Proposed: the persistent sidecar session

The sidecar dials groom and holds one WebSocket open (sidecar is the client,
groom the server — same direction as today's pushes, so no inbound reachability
into the container is needed). A reconnect-with-backoff loop means groom being
down is never fatal; the sidecar just keeps trying.

- **Advertise on connect.** The sidecar knows its own identity from env at launch
  — workflow id, workflow type, repo, branch, run id, volume paths — and sends it
  in a `hello` frame. groom no longer needs `docker inspect` for connected
  containers.
- **Liveness = connection.** An open socket *is* "running"; a close is "gone".
  This replaces the reconcile-and-prune heuristic for the running fleet.
- **Reliable-on-reconnect.** A single session gives ordering; re-advertising full
  current state on reconnect self-heals across a groom restart. This is the
  correctness the poll used to provide.
- **Data plane over the same socket.** groom issues `getTree` / `getFile` /
  `getDiff` requests; the sidecar answers from local disk (and may maintain the
  tree incrementally from `inotify`, and stream diff deltas). Because the
  container isn't reachable by inbound HTTP, this is request/response **over the
  sidecar-dialed socket** (correlation ids + timeouts) — a small RPC surface,
  distinct from the browser `/ws`.

`groom.app`'s `/files` / `/file` / `/diff` handlers prefer the socket when a
container is connected. The `safe_relpath` traversal guard moves into the sidecar
(the read now happens there).

## Scope decisions (explicit non-goals)

- **No stopped/legacy-container support for the interactive data plane.** We do
  not build tooling to browse files/diffs of a container without a live, current
  sidecar. The interactive data plane is **sidecar-only** — the
  throwaway-container volume reads for Files/Diff can be retired once the sidecar
  serves them.
- **Upgrade by recreation, not by coping.** To run a newer sidecar, **recreate**
  the container from a fresh image against the **same** `workspace`/`runs`
  volumes, same `/workflow` bind, same env. workhorse resumes from
  `checkpoint.json`. This is safe because:
  - The workflow *graph* is the `/workflow` **host bind mount**, not baked into
    the image — a new image gives a new sidecar/runtime **without** changing the
    graph, so the checkpoint's `current_id` still lines up.
  - The gate is **idempotent on resume**: the answer is the `STATUS:` line
    persisted in the `/workspace` context file, so recreating mid-gate re-reads it
    and either proceeds or blocks again.
- **"Restart" means recreate, not `docker start`.** `docker start` reuses the
  same (old) image and sidecar; a newer sidecar requires `docker rm` + `docker
  run`, or `docker compose up -d --force-recreate <svc>`. Since these containers
  are compose-managed, lean on compose rather than reconstructing the run spec
  from `docker inspect`.
- **Two edges to respect when recreating:** the checkpoint is **node-granular**
  (recreating mid-node re-runs that node from its start — bounded lost work; only
  offer recreate when blocked/idle), and it is only graph-compatible while the
  `/workflow` bind is unchanged (changing the graph is a different operation that
  may not resume).
- **No host groom self-restart.** groom runs in the operator's terminal;
  restarting it is a manual `Ctrl-C` + rerun. Browser tabs (htmx-ext-ws) and
  sidecars (reconnect loop) re-dial and re-advertise, and the startup reconcile
  scan repopulates `WORKFLOWS`, so a host restart is near-invisible and needs no
  graceful self-exec.

## Development loop: bind mount + copy-on-start

Iterating on `groom/sidecar.py` should not require an image rebuild. Until groom
is published to PyPI (at which point the story becomes "`pipx upgrade` +
reload"), use a bind mount — placed **directly in the repo's `compose.yaml`**,
not a separate override. The image is the repo's own dev/reference harness (it is
not shipped with the `workhorse-agent` PyPI package, and third parties bring
their own image), so there is no external consumer whose build-time immutability
must be protected.

The process must **not** run straight off the live bind — a mid-save on the host
would expose partial files, and the bind carries host ownership rather than the
`nobody`-readable perms the sidecar needs. Instead:

- Bind the host groom source to a **read-only staging path**, e.g.
  `/mnt/groom-src:ro`.
- The entrypoint **copies** `/mnt/groom-src` → `/app/groom` (the location `uv run`
  resolves the editable package from) with `chown nobody` + `a+rX`, on startup and
  before **every** relaunch. The running copy is thus always private and
  correctly-permissioned, and the copy is what picks up an edit.

This keeps the baked `COPY groom/` in the base Dockerfile for release; the bind
mount only shadows it during development.

## Sidecar reload

Reloading the sidecar to pick up edited code is a **supervised restart**, not a
self-`execv`. The key constraint: **the recopy must happen while the sidecar is
not running** — a process cannot cleanly copy over its own imported source and
re-exec from it. So the entrypoint (PID 1) owns a supervising loop and the
sidecar signals a reload by **exiting with code 3**:

```sh
copy_groom() {
  cp -a /mnt/groom-src/. /app/groom/      # or rsync --delete
  chown -R nobody:nogroup /app/groom
}

run_sidecar() {
  while :; do
    copy_groom
    gosu nobody env HOME=/claude-state PYTHONDONTWRITEBYTECODE=1 \
      uv run groom-sidecar
    rc=$?
    [ "$rc" = 3 ] || break                # 3 = reload request; anything else = stop
  done
}
run_sidecar &                             # workhorse stays the foreground/PID-forwarded process
```

- **Trigger is a manual, socket-broadcast reload**, not `inotify` on the source.
  groom sends a `reload` command over the sockets it already holds; the sidecar
  cleanly closes and `exit(3)`s; the entrypoint recopies the edited source and
  relaunches; the new process re-dials and re-advertises. Not watching the source
  removes the `__pycache__` feedback loop, debouncing, and compile-guarding that
  automatic detection would need. (`PYTHONDONTWRITEBYTECODE=1` above is belt-and-
  suspenders against pyc churn.)
- **Fleet-wide by construction.** Because groom holds a socket to every sidecar,
  one edit + one broadcast reloads the whole fleet — or a single container, since
  the operator picks the blast radius. Reloading does **not** perturb running
  workflows: the sidecar is a background helper; workhorse in the foreground never
  notices.
- **Manual timing removes the race.** The operator reloads *after* saving, so a
  recopy never races a half-written file; the stage-and-`mv` atomicity precaution
  is optional.
- **Bad-code recovery.** If a reload lands on code that fails to import, the
  sidecar exits non-3, the loop stops, and it stays down (the safe failure — no
  restart storm). Recovery without a shell into the container: `docker restart
  <cid>` reruns the entrypoint, which recopies the now-fixed source and relaunches;
  the workflow resumes from checkpoint.

## Invariants (load-bearing)

- **Non-authoritative sidecar, ephemeral state, resync on connect.** Never make a
  connection or in-memory datum the only copy of something that matters; a
  reconnect must be able to rebuild it. This is what makes every restart cheap.
- **Fire-and-forget discipline** on any residual best-effort push: short timeout,
  silent on failure, never blocks the workflow or changes its exit code (see
  [sidecar-protocol](sidecar-protocol.md)).
- **Recopy while down.** The sidecar reload path never copies over its own running
  source; the supervising shell recopies *between* runs. `exit(3)` is the
  handoff and is reserved for intentional reload (outside 0/1/2, 126/127,
  128+signal).
- **Traversal guard travels with the read.** When a file read moves into the
  sidecar, `safe_relpath` (or its equivalent) moves with it — the sidecar is an
  unauthenticated file server for its own volume.
- **Graph lives in the bind, runtime in the image.** Preserve the separation that
  makes recreate-to-upgrade safe: never bake a workflow's graph into the image.

## Open questions

- Exact socket message schema: the `hello` frame, the `getTree`/`getFile`/`getDiff`
  RPC envelope (correlation ids, error shape), and the `reload` command.
- `inotify` overflow (`IN_Q_OVERFLOW`) and rename handling for an incrementally
  maintained file tree — likely "on overflow, full rescan".
- Whether any volume-read fallback is worth keeping for a *finished* run's
  files/diff, or whether "recreate to review" is always acceptable (current
  decision: recreate; no fallback).
- Backpressure/coalescing for streamed diff deltas on a busy checkout.

## Related

- [sidecar-protocol](sidecar-protocol.md) — the current two-way push/pull channel
  this evolves.
- [sidecar-autostart](sidecar-autostart.md) — how the sidecar is launched and
  baked into the image today.
