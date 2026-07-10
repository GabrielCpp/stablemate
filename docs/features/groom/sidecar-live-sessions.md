---
type: feature
slug: sidecar-live-sessions
title: Sidecar live sessions — persistent socket data plane + dev reload
status: implemented
id: stablemate-6
area: groom
---
# Sidecar live sessions — persistent socket data plane + dev reload

**Status: implemented.** This evolves the earlier best-effort push/pull channel
(see [sidecar-protocol](sidecar-protocol.md)) into a persistent, stateful
session and uses that session as the data plane for groom's interactive panels.
It also ships the local development loop for iterating on the sidecar without an
image rebuild. See the [Implementation](#implementation) section for the
concrete message schema and where each piece lives.

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

## Development loop: editable uv tool from a bind

Iterating on `groom/sidecar.py` should not require an image rebuild. groom is
**not baked** into the image; it is installed at container start as an editable
uv **tool** — the `pipx install --editable` model — from a bind of the host
`groom/` source:

- Bind the host groom source read-only, e.g. `../groom:/mnt/groom-src:ro`
  (**directly in the repo's `compose.yaml`**, not a separate override).
- The entrypoint runs `uv tool install --editable /mnt/groom-src --no-sources`,
  which installs `groom-sidecar` into an isolated tool venv under
  `HOME=/claude-state` and points it at the live bind. The install is idempotent
  and the tool venv + uv cache persist on the `claude-state` volume, so only a
  fresh volume's first start pays a download.

Two subtleties, both handled:

- **`--no-sources`.** groom declares `workhorse-agent = { workspace = true }` in
  `tool.uv.sources`, so a plain `uv sync`/`uv pip install` refuses to build it
  outside the uv workspace. `pip`/`pipx` ignore `tool.uv.sources` entirely, and
  `--no-sources` is uv's equivalent — it installs groom **standalone**, pulling
  `workhorse-agent` and groom's deps from PyPI. (So groom *can* be a standalone
  editable install; it is only `uv`'s workspace-aware resolvers that couple it.)
- **Running off a read-only bind.** No copy is needed: the bind is world-readable,
  `PYTHONDONTWRITEBYTECODE=1` stops `.pyc` writes into it, and a reload is done
  manually after a save (no partial files). The editable install writes only into
  its own tool venv, never back to the host checkout.

Because it is editable, a reload just **restarts** the process — the live bind
source is re-imported, no reinstall. Without the bind, nothing is installed and
the container simply runs without a sidecar (the sidecar is best-effort). When
groom eventually ships to PyPI this becomes a literal `pipx install --editable` /
`uv tool install` from the index instead of a bind.

## Sidecar reload

Reloading the sidecar to pick up edited code is a **supervised restart**, not a
self-`execv`: a process can't cleanly re-exec from its own imported source. So
the entrypoint (PID 1) owns a supervising loop and the sidecar signals a reload
by **exiting with code 3**. Because the install is *editable* off the bind, the
restart alone picks up the edit — no copy, no reinstall:

```sh
# once, at startup (installs groom-sidecar into an isolated tool venv, editable
# off the live bind; --no-sources pulls workhorse-agent + deps from PyPI):
gosu nobody env HOME=/claude-state UV_TOOL_BIN_DIR=/claude-state/.local/bin \
  uv tool install --editable /mnt/groom-src --no-sources

run_sidecar() {
  while :; do
    gosu nobody env HOME=/claude-state PYTHONDONTWRITEBYTECODE=1 \
      /claude-state/.local/bin/groom-sidecar
    rc=$?
    [ "$rc" = 3 ] || break                # 3 = reload request; anything else = stop
  done
}
run_sidecar &                             # workhorse stays the foreground/PID-forwarded process
```

- **Trigger is a manual, socket-broadcast reload**, not `inotify` on the source.
  groom sends a `reload` command over the sockets it already holds; the sidecar
  cleanly closes and `exit(3)`s; the entrypoint restarts it and the new process
  re-imports the live bind source, then re-dials and re-advertises. Not watching
  the source removes the `__pycache__` feedback loop, debouncing, and
  compile-guarding that automatic detection would need. (`PYTHONDONTWRITEBYTECODE=1`
  above also keeps the read-only bind free of `.pyc` churn.)
- **Fleet-wide by construction.** Because groom holds a socket to every sidecar,
  one edit + one broadcast reloads the whole fleet — or a single container, since
  the operator picks the blast radius. Reloading does **not** perturb running
  workflows: the sidecar is a background helper; workhorse in the foreground never
  notices.
- **Manual timing removes the race.** The operator reloads *after* saving, so the
  restart never re-imports a half-written file.
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

## Implementation

The sidecar dials `ws://$GROOM_HOST:$GROOM_PORT/sidecar` and holds it open;
groom's `dashboard_sidecar` handler accepts it. All frames are JSON with a
`type` discriminator.

**Sidecar → groom**

- `{"type":"hello", "identity":{container_id,name,repo_name,repo_branch},
  "snapshot":{current_node,terminal,gates:[{file_path,question}]}}` — sent on
  every (re)connect. groom folds it in (`_apply_hello`), rebuilding gates
  **authoritatively** from the snapshot. `identity` carries only what the
  container env exposes; the docker-level bits (workflow type, volume names)
  are still resolved once via `_ensure_volumes` (`docker inspect`) for the
  answer/fallback paths.
- `{"type":"progress","current_node":…}` / `{"type":"blocked",file_path,question}`
  — inotify deltas, streamed over the same socket (`_apply_socket_progress` /
  `_apply_socket_blocked`).
- `{"type":"rpc_result","id":…,"ok":true,"data":…}` or
  `{…,"ok":false,"error":…}` — the reply to one RPC.

**groom → sidecar**

- `{"type":"rpc","id":…,"method":"getTree"|"getFile"|"getDiff","params":{repo,path}}`
  — correlation id is a per-connection counter (`SidecarConnection`), answered
  from local disk. `getTree`→`{paths:[…]}`, `getFile`→`{content}`,
  `getDiff`→`{diff}`.
- `{"type":"reload"}` — the sidecar closes and `exit(3)`s.

**Decisions on the former open questions**

- **Volume-read fallback is kept** (a strictly-better superset of the
  "retire it" non-goal): `/files` `/file` `/diff` prefer the socket and fall
  back to the throwaway-container read when no sidecar is connected, so a
  stopped/finished/legacy container is still browsable. `_sidecar_rpc` returns
  `None` on no-connection-or-error and the handler drops through.
- **Liveness is soft.** A socket close unregisters the RPC connection (and fails
  its in-flight RPCs) but does **not** delete the workflow row — the reconcile
  scan still owns removal, so a transient drop or a groom restart doesn't flap
  the fleet. Re-advertise-on-reconnect is what restores authority.
- **`inotify` overflow / streamed-diff backpressure / coalescing** are not yet
  optimized: the tree is walked per `getTree` (not incrementally maintained) and
  diffs are request/response, not streamed deltas. The socket + fallback shape
  leaves room to add incremental maintenance later without a protocol change.

**Where it lives**

- `groom/groom/sidecar.py` — the async session (`run`/`_serve`/`_run_session`),
  RPC handlers (`_rpc_get_tree`/`_rpc_get_file`/`_rpc_get_diff`, `_safe_relpath`),
  `_hello_frame`, `_classify_event`, `ReloadRequested`/`RELOAD_EXIT_CODE`.
- `groom/groom/sidecar_hub.py` — host-side `SidecarConnection` (RPC correlation,
  send lock) + the `CONNECTIONS` registry.
- `groom/groom/app.py` — `dashboard_sidecar` (`/sidecar`), the socket-preferred
  `/files`/`/file`/`/diff`, `/reload`, `_apply_hello`.
- `workhorse/entrypoint.sh` — `uv tool install --editable /mnt/groom-src
  --no-sources` at startup, then the `run_sidecar` exit-3 supervising loop
  (restart-only; the editable install makes edits live). `workhorse/Dockerfile`
  — does **not** bake groom (drops `COPY groom/` + `--package groom`); groom is
  the editable tool installed at runtime. `workhorse/compose.yaml` — the
  read-only `../groom:/mnt/groom-src` bind; `farrier`'s generated compose
  (`farrier/farrier/install.py`) emits the same bind commented, gated on
  `GROOM_SRC`, so a consuming repo (e.g. predykt) can install the sidecar.
  `groom/pyproject.toml` — the `websockets` dependency.
- Tests: `groom/tests/test_sidecar_hub.py`, `test_sidecar_session.py`, and the
  socket-path/`/reload`/`hello` cases in `test_app.py`.

## Related

- [sidecar-protocol](sidecar-protocol.md) — the current two-way push/pull channel
  this evolves.
- [sidecar-autostart](sidecar-autostart.md) — how the sidecar is launched and
  baked into the image today.
