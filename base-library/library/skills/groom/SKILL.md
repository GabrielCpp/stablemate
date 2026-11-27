---
name: groom
description: "groom, the operator-gate dashboard and push service for workhorse runs. Load when integrating a workflow or script with groom: gate files, the sidecar, backstop pushes, or the signal model."
tags: [python, backend, standards]
---

# Groom

Load this skill when a `workhorse` workflow's operator-gate wait scripts need to change, when
a script must tell groom about a run, or when explaining how blocked workflow containers become
visible to a human operator.

**Reading a run rather than building one** — where is it stuck, why does that loop repeat,
what did it cost, what did the node actually say — is [[groom-telemetry]], which covers the
SQLite store and the turn-record archive beside it. **Acting on a run** — reloading it onto
pushed code, switching its CLI, answering its gate from the terminal — is [[workhorse-operate]].
This skill is groom's integration contract; those two are its evidence and its levers.

For a one-shot read of "what's been alive or dead recently, ordered by telemetry" across the
whole store — the gap `groom status` (liveness from the server's heartbeat cache) leaves
for runs whose process vanished an hour ago, and `groom archive ls` (terminal-and-archived)
leaves for the in-between — the answer is `groom recent`, surfaced under [[groom-telemetry]].
Three views of "what runs are out there", deliberately scoped so each one says something the
others cannot.

## What it is

`groom` gives a local web dashboard with push notifications on new operator gates and a
one-click answer flow, for `author`/`coder` workflow containers run via `workhorse` + Docker
Compose. `pipx install stablemate` puts `groom` and `groom-sidecar` on the PATH. It needs zero
repo-specific knowledge: containers are identified generically (the `/workflow` bind mount +
`/runs`/`/workspace` volumes that are `workhorse`'s own compose convention), and gates are found
by scanning for a `STATUS: AWAITING_OPERATOR` line, not a hardcoded path table.

Manual launch only — `groom serve` in a terminal/tmux pane for the session. No systemd unit, no
auto-start, no compose service for `groom` itself. `groom serve` refuses a non-loopback `--host`
without `--allow-non-loopback`.

## Signal model — push, not host-side polling

Workflow state lives in named Docker volumes invisible to a host-side `inotify` watch, so `groom`
doesn't poll. Instead:

- **`groom-sidecar`** runs *inside* the agent container (baked into the image by workhorse's
  Dockerfile), watches `/workspace`+`/runs` via `watchfiles`, and POSTs `progress`/`blocked`
  events to the host's `groom` at `http://host.docker.internal:8787/...`.
- **Fire-and-forget, always.** Every push is a short-timeout (1.0s) HTTP call wrapped in a broad
  `except: pass` — never retries, never raises. A container with no `groom` listening anywhere
  behaves identically to one with `groom` attached. Preserve this discipline in any new push
  site; a workflow must never depend on `groom` being up.
- **The wait script itself also pushes** a `blocked` event each time it shows a new or re-armed
  gate banner, using the same fire-and-forget call. This is a redundant backstop the server
  treats idempotently. The wait script blocks in place on its own `inotify` watch of the gate
  file and only exits (`sys.exit(2)`) if raw inotify init itself fails.
- **`/feed` is the socket meant for a program, beside `/ws` for tabs and `/sidecar` for
  containers.** It carries one run: `event` frames the moment an alert fires, and a `digest`
  frame on a fixed interval even when nothing happened, so silence reads as a signal. The
  live clock keeps running while a feed is attached, with no tab open. `groom wait` is a
  client of the same feed that returns on the first matching event, and `groom feed` prints
  every frame.
- **Startup/on-demand reconciliation only.** `groom` scans the running containers once on its
  own startup and on `POST /refresh`. There is **no steady-state polling loop**.

## Answer flow (no restart in the common case)

An answer re-checks that the gate file still reads `AWAITING_OPERATOR`, so a second tab's stale
submission is rejected. It then writes `STATUS: ANSWERED` and the text into the container. A
running container's wait script wakes up in place, with no restart. A plain `docker start` is
only the fallback for a container that is not running.

## Notifications

Client-side only: a `blocked` push broadcasts a `{"type": "notify", "message": ...}` JSON frame
down the websocket; the dashboard's frame dispatcher raises an in-page toast and, when permission
has already been granted, a browser `Notification` (permission is requested from a user gesture on
page load, never from an incoming frame). No code is ever sent over the socket. There is no
server-side `notify-send` — paging requires a dashboard tab open with notification permission
granted.

## Network path

workhorse's own compose file adds `extra_hosts: ["host.docker.internal:host-gateway"]` to the
workflow service, so a container can always reach a loopback-bound `groom` on the host. No
per-repo change is needed.

## When writing a workflow's operator-gate scripts

If you add or modify an `await_*` wait script in a `workhorse` workflow, preserve: blocking in
place via `inotify` on the gate file (not exiting on block), the `blocked` push using the exact
fire-and-forget discipline above, and never assuming `groom` is running.
