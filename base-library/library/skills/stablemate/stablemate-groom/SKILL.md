---
name: stablemate-groom
description: "groom — the operator-gate dashboard and push-notification service for workhorse workflows: architecture, signal model, and how a workflow/script should integrate with it (gate-file convention, sidecar, backstop push)."
---

# Groom

Load this skill when working on `stablemate/groom/`, when a `workhorse` workflow's operator-gate
scripts (`await_operator.py`/`await-operator.py` and friends) need to change, or when explaining
how blocked workflow containers become visible to a human operator. Full as-built reference:
`stablemate/docs/features/groom.md`.

## What it is

`groom` is a standalone `stablemate` package — sibling to `workhorse/` and `farrier/`, never the
reverse dependency — that gives a local web dashboard with push notifications on new operator
gates and a one-click answer flow, for `author`/`coder` workflow containers run via `workhorse` +
Docker Compose. It needs zero repo-specific knowledge: containers are identified generically (the
`/workflow` bind mount + `/runs`/`/workspace` volumes that are `workhorse`'s own compose
convention), and gates are found by scanning for a `STATUS: AWAITING_OPERATOR` line, not a
hardcoded path table.

Manual launch only — `uv run groom serve` in a terminal/tmux pane for the session. No systemd
unit, no auto-start, no compose service for `groom` itself.

## Why not fold this into `workhorse`

`workhorse`'s job is running one workflow to completion in a container; it should not gain a web
server, a docker-control-plane surface, or UI dependencies. `groom` depends on `workhorse-agent` as
an ordinary library dep (for artifact/filename constants) — that dependency direction never
reverses.

## Signal model — push, not host-side polling

Workflow state lives in named Docker volumes invisible to a host-side `inotify` watch, so `groom`
doesn't poll. Instead:

- **`groom-sidecar`** runs *inside* the agent container (baked into the image via `stablemate`'s
  shared Dockerfile), watches `/workspace`+`/runs` with real `inotify` (`inotify_simple`), and
  POSTs `progress`/`blocked` events to the host's `groom` at `http://host.docker.internal:8787/...`.
- **Fire-and-forget, always.** Every push is a short-timeout (1.0s) `urllib.request` call wrapped
  in a broad `except: pass` — never retries, never raises. A container with no `groom` listening
  anywhere behaves identically to one with `groom` attached. Preserve this discipline in any new
  push site; a workflow must never depend on `groom` being up.
- **The wait script itself also pushes** (`_push_blocked_backstop()` in `await_operator.py`/
  `await-operator.py`) each time it shows a new or re-armed gate banner, using the same
  fire-and-forget call. This is a redundant, idempotent-on-the-server-side backstop, not a
  teardown race workaround — the wait script blocks in place on its own `inotify` watch of the gate
  file and only exits (`sys.exit(2)`) if raw inotify init itself fails.
- **Startup/on-demand reconciliation only.** `groom` runs a one-shot `discovery.scan()` on its own
  startup and on `POST /refresh` (`docker ps -a` + `docker inspect`, filtered to
  `/workflow`+`/runs`+`/workspace` mounts, gate files read via a throwaway read-only container).
  There is **no steady-state polling loop** — `discovery.py` has no answer/restart role.

## Answer flow (no restart in the common case)

`gates.py::answer_gate()`: acquire a per-`(container_id, file_path)` lock → re-check the gate file
still reads `AWAITING_OPERATOR` (reject a second tab's stale submission) → write `STATUS: ANSWERED`
+ the text via a throwaway read-write container (stdin-piped, never shell-interpolated) → if the
container is still running, done — the in-container wait script wakes up in place, no restart. A
plain `docker start <container_id>` is only a fallback for a container that isn't running (crashed,
manually stopped, or predates this design). **There is no compose/label-based recreate fallback.**

## Notifications

Client-side only: a `blocked` push triggers a websocket OOB swap carrying a `<script>` that
dispatches a `groom:blocked` `CustomEvent`; the dashboard's own JS turns that into a browser
`Notification` (permission requested once on page load). There is no server-side `notify-send` —
paging requires a dashboard tab open with notification permission granted.

## Stack constraints (don't violate these when touching `groom`)

- Python only — no Node/npm/bundler, including at packaging time.
- No runtime CDN — every asset (htmx, htmx-ext-ws, diff2html, marked, DOMPurify, Pico classless
  CSS) is vendored under `groom/assets/` and served via `create_static_files_router`.
- Single-process, shared in-memory state — `state.py`'s `WORKFLOWS`/`LOG`/`CLIENTS`/`_gate_locks`
  are plain module-level objects, not Litestar `app.state`, not Redis/a broker.
- Litestar + htmx/htmx-ext-ws: server pushes `hx-swap-oob` HTML fragments over one websocket;
  controls are `ws-send` forms. `_handle_command` recognizes only `cmd == "answer"`.
- Agent-authored content (gate questions, diffs) is rendered client-side from escaped text nodes
  (`marked`+`DOMPurify`, `diff2html`) — never raw server-rendered HTML, to keep an XSS-safe
  boundary (`tests/test_render.py` is the contract to preserve).
- `groom serve` refuses a non-loopback `--host` without `--allow-non-loopback`.

## Accessibility (the dashboard is a real UI — it owes the contract)

groom's stack is exactly the one [`{{ instruction_file("python-htmx-accessibility") }}`]({{ instruction_file("python-htmx-accessibility") }})
governs — server-rendered `templates/dashboard.html` + HTMX/`hx-ext="ws"` + vanilla JS, no bundler
— which in turn realizes the universal
[`{{ instruction_file("ui-accessibility") }}`]({{ instruction_file("ui-accessibility") }}) contract. Load
both when touching the template or `assets/*.js`. Concrete gaps in the dashboard as built (fix these
to the contract, don't add more like them):

- `#palette` is a role-less `<div>` overlay — it must be `role="dialog"` + `aria-modal`, trap focus,
  move focus to `#palette-input` on open, and Escape-restore focus to the trigger; `#palette-results`
  must be a `role="listbox"` with `role="option"` rows driven by `aria-activedescendant`.
- `#palette-input` and the `.filter` input have only a `placeholder` — each needs a real (optionally
  sr-only) `<label>` or `aria-label`.
- The websocket OOB targets (worker cards, the log, the blocked-gate banner) must be stable
  `aria-live` regions — `role="status"`/`"log"` for progress, `aria-live="assertive"` for a new
  blocked gate — or a screen-reader operator never hears a container went blocked.
- The `.ws-dot` "live" indicator conveys state by color alone — pair it with text/an icon.

The `marked`+`DOMPurify` markdown path already preserves the XSS boundary
(`tests/test_render.py`); keep it also preserving headings/lists so gate questions stay perceivable.

## Package layout (orientation, not exhaustive — see groom.md for the full tree)

`models.py` (dataclasses) · `state.py` (in-memory store + broadcast) · `gates.py` (STATUS
parsing + `answer_gate`) · `docker_io.py` (purpose-built throwaway-container helpers:
`read_file`/`write_file`/`grep_awaiting_files`/`docker_start`/`is_running`/`git_diff`/...) ·
`discovery.py` (one-shot reconciliation) · `render.py` (HTML fragments) · `app.py` (Litestar
routes + `/ws`) · `sidecar.py` (in-container `groom-sidecar`) · `cli.py` (`groom`/`groom-sidecar`
entry points).

## Network path

`farrier`'s generated compose template adds `extra_hosts: ["host.docker.internal:host-gateway"]`
to every workflow service (see [[farrier-setup]]), so a container can always reach a
loopback-bound `groom` on the host — this is already generated into every consuming repo's
`.agents/local.compose.yaml`; no per-repo change needed.

## When touching a workflow's operator-gate scripts

If you add or modify a `await_*` wait script in a `workhorse` workflow (see [[coder-workflow]] for
the node-topology conventions), preserve: blocking in place via `inotify` on the gate file (not
exiting on block), the `_push_blocked_backstop()` call using the exact fire-and-forget discipline
above, and never assuming `groom` is running.
