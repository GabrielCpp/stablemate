---
type: feature
slug: groom
title: groom — operator-gate dashboard and push notifications
status: implemented
---
# `groom` — operator-gate dashboard and push notifications

> **Surfaces (per-surface Concepts):** [operator-inbox](operator-inbox.md) ·
> [worker-tree](worker-tree.md) · [changes-view](changes-view.md) ·
> [sidecar-protocol](sidecar-protocol.md) ·
> [sidecar-autostart](sidecar-autostart.md). This doc is the architecture
> overview; each Concept above documents one as-built surface.

Status: **implemented** (2026-07-06) — `stablemate/groom/` (Litestar app, in-container sidecar,
vendored htmx/diff2html UI, `tests/test_*.py`); wired into `farrier`'s generated compose template
(`extra_hosts: host.docker.internal`) and into `vigilant-octo/agents`' shared `await_operator.py`
scripts (backstop push). This doc originally shipped as a pre-implementation design brief; it has
since been rewritten to describe the architecture as built, most notably around the answer/restart
flow, which turned out simpler than planned once the in-container wait script was redesigned to
block via `inotify` instead of exiting.

## Context

`author`/`coder` autonomous workflows (run via `workhorse` + Docker Compose, defined in the
central `vigilant-octo/agents` prompt library and consumed by repos like Predykt) block on
"operator gates": the in-container wait script (`await_operator.py`/`await-operator.py`) parks on
an `inotify` watch of the gate file until its `STATUS:` line flips to `ANSWERED`, then resumes in
place. With more than one workflow running at once, having no aggregate visibility — no dashboard,
CLI status view, or notification of any kind — meant the only way to know a workflow was blocked
was to notice its container had stopped progressing and dig into its `docs/**/*.md` context file
by hand.

`groom` is a standalone `stablemate` package — sibling to `workhorse/` and `farrier/` — that gives
a local web dashboard with push notifications on new blocks and a one-click answer flow. It ships
alongside a companion fix in `vigilant-octo/agents` (a self-verification gap in several of
author's gates, tracked separately, not detailed here) that reduces how often gates re-block in
the first place.

## Why a separate package, not `workhorse dashboard`

1. **workhorse's core job is running one workflow to completion in a container** — it should not
   gain a web server, a docker-control-plane surface, or UI dependencies just because a monitoring
   tool happens to read its artifact format. Those are unrelated concerns with their own release
   cadence and dependency footprint. `groom` depends on `workhorse` (`workhorse-agent` on PyPI) as
   an ordinary library dependency — never the reverse. `workhorse`'s own `pyproject.toml` gains
   nothing from this feature.
2. **Run mode: manual launch, not an auto-starting daemon.** No systemd unit, no auto-start on
   login/boot, no docker-compose service for `groom` itself. The user runs it themselves (e.g.
   `uv run groom serve` in a terminal or tmux pane) for the duration of a work session — "always
   watching" comes from the process being long-lived while active, not from being auto-started.

`groom` needs zero repo-specific knowledge to work: workflow containers are identified generically
(bind mount at `/workflow` + volume mounts at `/runs`/`/workspace` — workhorse's own compose
convention, inherited by every consuming repo), repo identity comes from each container's own env,
and gate files are found by scanning for a `STATUS: AWAITING_OPERATOR` line rather than any
hardcoded path table (gate context-file paths genuinely vary per node: `_author-context.md`,
per-story `context.md`, per-epic `ci-operator-context.md`, etc.).

## Stack constraints (load-bearing)

- **Python only.** No Node.js, npm, or bundler anywhere, including at packaging time.
- **No runtime CDN dependency.** All front-end assets (htmx, `htmx-ext-ws`, diff2html, marked,
  DOMPurify, Pico's classless CSS, `dashboard.css`) are vendored as static files inside the
  `groom` package (`groom/assets/`) and served locally.
- **Single-process, shared in-memory state.** No Redis, no broker. `state.py` holds
  `WORKFLOWS: dict[str, WorkflowContainer]`, `LOG: deque[dict]` (`maxlen=200`),
  `CLIENTS: set[asyncio.Queue]` (one queue per open websocket), and a lazily-created
  `_gate_locks: dict[str, asyncio.Lock]` keyed by `f"{container_id}::{file_path}"` — all plain
  module-level objects, not Litestar `app.state`.
- **Litestar** is the web framework (native websocket support, `create_static_files_router` for
  vendored assets). **htmx + htmx-ext-ws** drive reactivity: the server pushes HTML fragments with
  `hx-swap-oob` over one bidirectional websocket; the answer control is a `ws-send` form
  serialized to JSON.
- **Drop-in widgets only.** The answer textarea is a plain `<textarea>`. Gate questions and diffs
  are rendered client-side (`marked` + `DOMPurify` for markdown, `diff2html` for the working-tree
  panel) from escaped text nodes the server emits — never raw server-rendered HTML for
  agent-authored content, to keep an XSS-safe boundary (see `tests/test_render.py`).
- Assets are served from the package's own `assets/` directory via `create_static_files_router`,
  so serving is working-directory independent.

## Signal model: push via an in-container sidecar, not host-side polling

Workflow state (`/workspace`, `/runs`) lives in named Docker volumes, which aren't visible to a
host-side process for direct `inotify` watching, and host-side polling (`docker inspect`/`docker
run` on a timer) would mean both latency and a steady subprocess spawn rate.

Instead, **`groom` ships a second console script, `groom-sidecar`, that runs inside the agent
container itself** (installed into the agent image via `stablemate`'s shared Dockerfile;
`workhorse`'s own package/deps are untouched). `groom-sidecar` (`groom/sidecar.py`):

- watches `/workspace` and `/runs` recursively with real `inotify` (`inotify_simple`), skipping
  `.git`/`node_modules`/`__pycache__`/`.venv`, on `MODIFY | CLOSE_WRITE | CREATE | MOVED_TO`;
- on any qualifying event under `/runs` → POSTs a `progress` event (current node, read from the
  latest run dir's `checkpoint.json`) to `/push/progress`;
- on any file elsewhere whose `STATUS:` line reads `AWAITING_OPERATOR` → POSTs a `blocked` event
  (relative path + extracted question) to `/push/blocked`;
- targets the host's `groom` process at a fixed address (`http://host.docker.internal:8787/...`,
  `GROOM_HOST`/`GROOM_PORT` overridable via env);
- is **fire-and-forget and silent when unreachable**: every push wraps a short-timeout (1.0s by
  default) `urllib.request` call in a broad `except: pass`, never retries, never raises. This is
  the core safety property — a container running with no `groom` listening anywhere behaves
  identically to one with `groom` attached.

**Backstop push, not a teardown race.** The design originally assumed the container tears down
right after the wait script writes its halt file, racing the sidecar's own inotify callback. That
premise no longer holds: `await_operator.py`/`await-operator.py` now block in place on their own
`inotify` watch of the gate file and only ever call `sys.exit(2)` if the raw inotify syscalls fail
to initialize (a legacy/non-Linux fallback). What they *do* keep, unconditionally, is a
`_push_blocked_backstop()` call to the same `/push/blocked` endpoint each time they show a new (or
re-armed) gate banner — using the sidecar's exact fire-and-forget discipline (stdlib
`urllib.request`, 1.0s timeout, broad `except`). In practice this races the sidecar's own push
harmlessly: whichever POST lands first wins, the second is just a redundant re-render
(`app.py`'s `push_blocked` handler is idempotent for this reason).

**Startup/reconciliation scan**: since pushes only reach `groom` while both `groom` and the
sidecar are simultaneously up, a workflow that was *already* blocked before `groom` was started
this session would otherwise never be seen. `groom` runs a one-shot `discovery.scan()` on its own
startup (and on-demand via `POST /refresh`) — a `docker ps -a` + `docker inspect` batch, filtered
to containers with the `/workflow` bind mount and `/runs`/`/workspace` volumes, checking each's
gate files once via a throwaway read-only container (`docker_io.grep_awaiting_files`). No
steady-state polling loop exists otherwise — discovery is reconciliation-only, not a continuous
poller, and holds no role in answering or restarting containers.

## Network path: container → host `groom`

`farrier`'s generated compose service template (`farrier/install.py`, the source of every
consuming repo's `.agents/local.compose.yaml`) adds `extra_hosts: ["host.docker.internal:host-gateway"]`
to each workflow service, so every workflow container can always reach a loopback-bound `groom` on
the host at a fixed hostname regardless of which docker network the compose project uses (this
mapping is Linux-only-relevant; Docker Desktop on Mac/Windows already resolves
`host.docker.internal` via its VM proxy). `groom` **defaults to binding `0.0.0.0`** so the in-container sidecars can reach
it over the docker bridge (`host.docker.internal` → the bridge gateway on Linux, not loopback);
since groom has no auth, `serve()` prints a one-line exposure warning on any non-loopback bind
(`--allow-non-loopback` silences it, `--host 127.0.0.1` restores loopback-only). Run it only on
a trusted machine.

## Architecture — package layout

```
stablemate/groom/
    pyproject.toml       # name "groom"; deps: litestar[standard], workhorse-agent (workspace dep), inotify-simple
    groom/
        __init__.py
        models.py         # WorkflowState enum; GateInfo, WorkflowContainer, AnswerResult dataclasses
        state.py          # WORKFLOWS/LOG/CLIENTS/_gate_locks + mutators + async broadcast()
        gates.py          # status_of/is_awaiting/extract_question/apply_answer + answer_gate()
        docker_io.py      # docker_ps_all, docker_inspect, docker_start, is_running, safe_relpath,
                           # grep_awaiting_files, list_run_dirs, find_repo_dir, git_diff,
                           # read_file, write_file (each a purpose-built throwaway-container helper)
        discovery.py      # scan(): startup/on-demand reconciliation only, no answer/restart role
        render.py         # hx-swap-oob tbody fragments, diff toggle/panel, notify <script>, XSS-safe
        app.py            # Litestar app: routes + /ws, on_startup=[_startup_scan]
        sidecar.py         # groom-sidecar: inotify loop over /workspace + /runs -> push to host groom
        cli.py               # serve(), main(), sidecar_main() entry points
        assets/                # vendored: htmx.min.js, htmx-ext-ws.min.js, pico.classless.min.css,
                                # diff2html.min.{js,css}, marked.min.js, purify.min.js, dashboard.css
        templates/
            dashboard.html
    tests/
        test_gates.py       # STATUS parsing + answer_gate orchestration (mocked docker_io)
        test_discovery.py   # mount/env parsing against fixture docker-inspect JSON
        test_sidecar.py      # inotify-triggered event construction, fire-and-forget behavior
        test_render.py        # hx-swap-oob shape, XSS-safety of question/diff rendering
        test_docker_io.py       # throwaway-container helper argument shapes
```

**Route/websocket surface** (`app.py`):

| Route | Purpose |
| --- | --- |
| `GET /` | serves the static dashboard HTML |
| `GET /search?q=` | plain-string-filtered HTML fragment of rows |
| `GET /diff/{container_id}` | plaintext `git diff HEAD` for that workflow's working tree, lazily fetched by the UI's collapsible diff panel |
| `POST /refresh` | re-runs `discovery.scan()` on demand |
| `POST /push/progress` | sidecar's progress push handler; upserts `RUNNING` + `current_node`, broadcasts |
| `POST /push/blocked` | shared by the sidecar and the `await_operator.py` backstop push; upserts `BLOCKED`, records a `GateInfo`, broadcasts fragment + notify script |
| `WS /ws` | registers a per-connection queue in `CLIENTS`, sends the initial snapshot, then runs a send loop (queue → socket) and a recv loop (socket → `_handle_command`) concurrently |
| `GET /assets/*` | vendored static assets (`create_static_files_router`) |

`_handle_command` only recognizes `cmd == "answer"` — there is no `retry`/`pause`/`resume`
websocket command.

**Answer** (`gates.py::answer_gate(container_id, file_path, answer, *, workspace_volume)`), in
order:

1. Reject immediately if `workspace_volume` is unknown.
2. Acquire the per-`(container_id, file_path)` `asyncio.Lock` from `state.gate_lock()`.
3. Under the lock, re-read the gate file (`docker_io.read_file`, a throwaway read-only container);
   reject if it no longer reads `AWAITING_OPERATOR` (a second tab already answered it).
4. Flip its `STATUS:` line to `ANSWERED`, append the given text, and write it back
   (`docker_io.write_file`, a throwaway read-write container piping content via stdin — never raw
   shell interpolation of user-typed text).
5. Clear the gate from in-memory state so the UI stops showing a form for it.
6. **If the container is still running** (`docker_io.is_running`, a `docker inspect` check) —
   return `ok=True, "answered"`. This is the common case: the in-container wait script is parked
   on its own `inotify` watch of the same file and wakes up on the write, with no restart involved.
7. **Only if the container is not running** does it fall back to `docker_io.docker_start` (a plain
   `docker start <container_id>`) — for a container that predates this design, crashed, or was
   manually stopped. There is no `docker compose up -d` / compose-label / cached-env fallback
   anywhere in the code; if `docker start` itself fails, the message tells the operator to start
   the container manually.

**Notifications**: a `blocked` event (from either the sidecar push or the `await_operator.py`
backstop push) triggers a websocket OOB swap carrying a `<script>` that dispatches a client-side
`groom:blocked` `CustomEvent`. The dashboard's own JS listens for that event and raises a browser
`Notification` (permission requested once, on page load, via `Notification.requestPermission()`).
There is no server-side `notify-send` call — paging only works while a dashboard tab is open with
notification permission granted.

**UI**: one table, one row per workflow (idle/running/blocked/finished), with blocked rows showing
an expandable question banner (rendered client-side from markdown, sanitized with DOMPurify) and
an answer textarea + submit (`ws-send`). Search is htmx active-search
(`hx-get="/search"`, `hx-trigger="input changed delay:250ms"`) against plain Python string
filtering — no client-side search widget. Each row has a collapsible working-tree diff panel,
lazily fetched from `/diff/{container_id}` and rendered with the vendored `diff2html`.

## Non-goals / known gaps (carried by design, not bugs)

- **No automatic restart fallback beyond `docker start`.** A container that was actually removed
  (not just stopped) has no compose-based recreation path; the operator is told to start it
  manually. Revisit only if this proves to matter in practice.
- **No server-side desktop notification.** Paging depends on a browser tab staying open with
  notification permission granted; there is no headless/background paging channel.
- **No steady-state host-side polling.** Staleness between `groom` restarts and the next push (or
  a manual `/refresh`) is expected, not a bug — see Key risks.

## Key risks

- Multiple simultaneously-blocked gate files in one workflow → modeled as independent per-file
  `GateInfo` entities keyed by `(container_id, file_path)`, not assumed singular per workflow.
- Multi-tab race answering the same gate → per-gate `asyncio.Lock` + a re-check of the gate file's
  current status immediately before write.
- Container genuinely removed (not just stopped) → no automatic recovery; see Non-goals.
- Secrets in container env → read server-side only for the specific known keys `groom` needs
  (repo/container identity), never serialized into any API/websocket/log output.
- Non-loopback exposure → default now, so the sidecars can reach the host over the docker
  bridge; `groom serve` prints an exposure warning on any non-loopback bind (no auth), and
  `--host 127.0.0.1` restores loopback-only.
- Sidecar unreachable/crashed/missing, or `groom` itself not running → must be (and is) a pure
  no-op for the workflow; the wait script's own `inotify` loop and exit path never depend on
  either.
- `groom` restarted mid-session → the startup reconciliation scan is the only way already-blocked
  workflows get picked up; this is an expected staleness window, not a bug, until the next push or
  a manual `/refresh`.

## Verification

Automated: `make test` (from `stablemate/groom/`) runs `tests/test_*.py` directly under `uv run
python` — covers STATUS parsing/`answer_gate` orchestration (`test_gates.py`, mocked `docker_io`),
mount/env parsing against a fixture `docker inspect` blob (`test_discovery.py`), inotify-triggered
event construction and fire-and-forget behavior (`test_sidecar.py`), the `hx-swap-oob`
fragment shape and XSS-safety of question/diff rendering (`test_render.py`), and the
throwaway-container helper argument shapes (`test_docker_io.py`).

Manual: run `uv run groom serve` from `stablemate/groom` with no workflow containers running
(empty table, no crash). Start a workflow and confirm a `progress` push from `groom-sidecar`
reaches `groom` and updates the UI near-instantly (not on a poll cadence). Run it through to an
operator gate and confirm the `blocked` push lands and fires a browser `Notification` with the tab
open and permission granted. Answer a live gate through the UI while its container is still
running and confirm it resumes in place with **no restart** (the common case). Stop a blocked
container manually, then answer its gate through the UI, and confirm `groom` falls back to
`docker start` and the workflow resumes. Open two browser tabs on the same gate and confirm the
second submission is rejected once the first has been consumed. Stop `groom`, leave a workflow
container running, and confirm its behavior and eventual exit code are completely unaffected
(sidecar and backstop pushes fail silently). Restart `groom` against a still-blocked container
that existed before `groom` started and confirm the startup reconciliation scan picks it up.
Confirm `groom serve` (default `0.0.0.0`) binds and prints the exposure warning, and that
`groom serve --host 127.0.0.1` binds loopback-only without a warning. Confirm
`workhorse`'s own `pyproject.toml` and `main.py` are untouched by this package (`git diff --stat`
scoped to `stablemate/workhorse/` should be empty).
