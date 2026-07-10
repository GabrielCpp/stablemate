# groom

A local, single-process web dashboard for `workhorse` agent-workflow operator
gates. Run `groom serve` on your host while `author`/`coder` (or any other
`workhorse`-based workflow) containers run in the background; `groom` shows
every running workflow, pages you the moment one blocks on an operator gate,
and lets you answer the gate right from the browser — no more finding and
restarting blocked containers one by one. `await_operator.py` blocks in
place via `inotify` rather than exiting, so the container keeps running and
just wakes up once you answer; `groom` only falls back to `docker start` if
a container has genuinely stopped.

## How it works

- Each workflow container runs a tiny in-container sidecar, `groom-sidecar`,
  that watches its own `/workspace` and `/runs` mounts with `inotify` and holds
  one persistent WebSocket open to the host's `groom` (dialing out over
  `host.docker.internal`, so no inbound reachability is needed). It advertises
  full state on connect, streams `progress`/`blocked` deltas, and serves the
  Files/Diff panels from local disk via `getTree`/`getFile`/`getDiff` RPC over
  the same socket. The connection is best-effort and re-syncs on reconnect —
  a container with no `groom` listening behaves exactly as it does today. See
  `docs/features/groom/sidecar-live-sessions.md` for the message schema and the
  local `reload` dev loop.
- `groom` itself holds all state in memory (no database, no broker) and
  pushes updates to open browser tabs over a websocket using htmx +
  htmx-ext-ws. Gate questions render as Markdown (`marked`, sanitized with
  `DOMPurify` before insertion since the content is LLM-authored) and each
  workflow row can expand a `git diff` of its working tree (rendered with
  `diff2html`). All front-end assets are vendored locally; nothing is loaded
  from a CDN at runtime.
- On startup (or on-demand refresh), `groom` runs a one-shot `docker ps -a` +
  `docker inspect` reconciliation scan so workflows that were already
  blocked before `groom` was started are still picked up.

## Usage

```
uv run groom serve                # binds 0.0.0.0:8787 by default (see note below)
uv run groom serve --host 127.0.0.1   # loopback only (no container access)
```

> **Binding.** groom defaults to `0.0.0.0` so the in-container `groom-sidecar`s
> can reach it over the docker bridge (`host.docker.internal` → the bridge
> gateway on Linux, not loopback). groom has **no authentication** — it controls
> docker and answers operator gates — so only run it on a trusted machine; it
> prints a one-line warning on any non-loopback bind (`--allow-non-loopback`
> silences it). Use `--host 127.0.0.1` to bind loopback only.

See `docs/features/groom.md` at the repo root for the full design.
