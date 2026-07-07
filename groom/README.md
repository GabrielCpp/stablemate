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
  that watches its own `/workspace` and `/runs` mounts with `inotify` and
  pushes fire-and-forget HTTP updates to the host's `groom` process over
  `host.docker.internal`. Pushes are best-effort and silent on failure —
  a container with no `groom` listening behaves exactly as it does today.
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
uv run groom serve                # binds 127.0.0.1:8787 by default
```

See `docs/features/groom.md` at the repo root for the full design.
