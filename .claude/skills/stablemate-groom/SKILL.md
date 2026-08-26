---
name: stablemate-groom
description: "groom — the operator-gate dashboard and push-notification service for workhorse workflows: architecture, signal model, and how a workflow/script should integrate with it (gate-file convention, sidecar, backstop push)."
metadata:
  generated_by: farrier
  source: library/skills/groom/groom/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-groom/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [python, backend, standards]
---

# Groom

Load this skill when working on `stablemate/groom/`, when a `workhorse` workflow's operator-gate
scripts (`await_operator.py`/`await-operator.py` and friends) need to change, or when explaining
how blocked workflow containers become visible to a human operator. Full as-built reference:
`stablemate/docs/features/groom.md`.

**Reading a run rather than building one** — where is it stuck, why does that loop repeat,
what did it cost, what did the node actually say — is [[groom-telemetry]], which covers the
SQLite store and the turn-record archive beside it. This skill is groom's architecture; that
one is its evidence.

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
  shared Dockerfile), watches `/workspace`+`/runs` via `watchfiles` (inotify in the container,
  FSEvents/ReadDirectoryChangesW on a developer machine), and
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

Client-side only: a `blocked` push broadcasts a `{"type": "notify", "message": ...}` JSON frame
down the websocket; the dashboard's frame dispatcher raises an in-page toast and, when permission
has already been granted, a browser `Notification` (permission is requested from a user gesture on
page load, never from an incoming frame). No code is ever sent over the socket. There is no
server-side `notify-send` — paging requires a dashboard tab open with notification permission
granted.

## Stack constraints (don't violate these when touching `groom`)

- Python only — no Node/npm/bundler, including at packaging time.
- No runtime CDN — every asset (the `htm/preact` standalone ESM build, diff2html, marked,
  DOMPurify, highlight.js, Pico classless CSS, `dashboard.js`) is vendored under `groom/assets/`
  and served via `create_static_files_router`.
- Single-process, shared in-memory state — `state.py`'s `WORKFLOWS`/`LOG`/`CLIENTS`/`_gate_locks`
  are plain module-level objects, not Litestar `app.state`, not Redis/a broker.
- **Everything on the wire is JSON.** The server never emits markup: `projection.py` builds the
  payloads, and the *same* shapes go out over `/ws` and over HTTP (`/api/state` and friends), so a
  tab whose socket went quiet resyncs rather than going stale. One state shape, one render path.
  `_handle_command` recognizes `cmd == "answer"` and `cmd == "watch"`.
- The browser renders with Preact + htm, mounted as islands into ids the static shell already
  ships. **No build step, no `package.json`, no `node_modules`** — the vendored standalone build is
  an ESM module loaded directly. Keep it that way; the Python-only constraint above is why.
- Connection state is derived from **message recency, not `readyState`** (a half-open socket reads
  open forever): live / stale / reconnecting / offline, with HTTP resync polling once stale.
- Agent-authored content (gate questions, diffs) is rendered client-side from JSON string members
  (`marked`+`DOMPurify`, `diff2html`) — the server emits no markup at all, which is what keeps the
  XSS boundary in one place (`tests/test_dashboard_client.py` is the contract to preserve).
- `groom serve` refuses a non-loopback `--host` without `--allow-non-loopback`.

## Accessibility (the dashboard is a real UI — it owes the contract)

The universal [`../stablemate-ui-accessibility/SKILL.md`](../stablemate-ui-accessibility/SKILL.md)
contract applies and is the skill to load. There is **no per-stack skill for groom's stack** — it is
a hand-authored HTML shell plus Preact islands with no router and no bundler, so the framework
mechanics the stack skills exist to supply (HTMX swap/focus rules, React Router announcements)
don't apply.

> **Ignore `stablemate-python-htmx-accessibility` when you are in `groom/`.** It is still installed
> — the universal contract skill routes to it, and farrier follows that link — and its `applyTo`
> glob matches `groom/templates/**` and `groom/assets/**/*.js`. It describes a stack groom left:
> there is no `hx-swap` here, no out-of-band push, no server-rendered fragment. Following it means
> rebuilding machinery that was deliberately removed.

The mechanics that do apply are small enough to state here:

- **The live regions are in the shell, not in the islands.** `#runs-list` (`role="log"`),
  `#statusbar` and the detail head (`role="status"`), and `#toasts` (`role="alert"`,
  `aria-live="assertive"`) are static elements the islands render *into*. Keep it that way: a live
  region that is itself re-created by a render is never announced. Adding a fourth `role="status"`
  to this page needs a distinguishing `aria-label` — the ambiguity is real and `ostler locators`
  will catch it.
- **Every island's roots and names are the accessibility contract.** Rows are keyed so Preact
  reconciles rather than replaces; a key change that swaps a row's DOM node moves focus off it.
- **State is never colour alone.** The connection chip and `.ws-dot` pair the dot
  (`aria-hidden="true"`) with the phase word; run status pairs its colour with text.
- **The command palette is a modal:** `role="dialog"` + `aria-modal`, focus moved to
  `#palette-input` on open and restored to the trigger on Escape, with the input as a `combobox`
  driving `aria-activedescendant` over a `role="listbox"`. The repo search box follows the same
  pattern. Both are built; don't regress them.

**Accessibility here is tested dynamically, not statically.** `tests/test_a11y_dynamic.py` drives
a live groom with Playwright and runs vendored axe-core over each pane. Adding a pane means adding
its axe pass — a static template linter cannot see markup the browser builds.

The `marked`+`DOMPurify` markdown path preserves the XSS boundary
(`tests/test_dashboard_client.py`); keep it also preserving headings/lists so gate questions stay
perceivable.

## Package layout (orientation, not exhaustive — see groom.md for the full tree)

`models.py` (dataclasses) · `state.py` (in-memory store + broadcast) · `gates.py` (STATUS
parsing + `answer_gate`) · `docker_io.py` (purpose-built throwaway-container helpers:
`read_file`/`write_file`/`grep_awaiting_files`/`docker_start`/`is_running`/`git_diff`/...) ·
`discovery.py` (one-shot reconciliation) · `projection.py` (registry → the JSON payloads both
transports send) · `app.py` (Litestar routes + `/ws`) · `assets/dashboard.js` (the Preact
islands) · `sidecar.py` (in-container `groom-sidecar`) · `cli.py` (`groom`/`groom-sidecar` entry
points).

## Network path

`workhorse/compose.yaml` adds `extra_hosts: ["host.docker.internal:host-gateway"]` to the workflow
service, so a container can always reach a loopback-bound `groom` on the host; no per-repo change
needed. (farrier used to generate a per-repo `.agents/local.compose.yaml` carrying the same
mapping. It installs skills and prompts only now and generates no compose file at all — the
mapping lives in workhorse's own compose file.)

## When touching a workflow's operator-gate scripts

If you add or modify a `await_*` wait script in a `workhorse` workflow (see [[coder-workflow]] for
the node-topology conventions), preserve: blocking in place via `inotify` on the gate file (not
exiting on block), the `_push_blocked_backstop()` call using the exact fire-and-forget discipline
above, and never assuming `groom` is running.
