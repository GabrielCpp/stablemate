---
type: runbook
slug: groom-local-serve
title: groom local server
---
# groom local server

- driver: web
- environment: [local Python uv workspace](local-python-uv-workspace.md)
- cli: [groom](../groom-cli.md)
- surfaces: [groom HTTP API](../http/groom.md)
- code: `groom/groom/cli.py::serve`
- entry-url: `http://127.0.0.1:8787`
- health-path: `/api/state`
- identity: `"workflows"` — the JSON response body contains a `"workflows"` key (an object literal, structure subject to change)
- reuse: never
- fresh: none
- boot-timeout: 10
- health-timeout: 5
- stop: `SIGINT` (Ctrl+C) or `SIGTERM`
- working-directory: `.`

The groom server is a Litestar ASGI web application that collects telemetry from workflow
containers running under Docker Compose and exposes a dashboard via HTTP and WebSocket. It
observes workhorse agent runs live, displays operator gates waiting for human approval, handles
gate answers, and streams run telemetry through an in-memory store. The server is launched
manually and runs as a single Python process on the host machine (not in a container) for the
duration of a work session. It has a graceful shutdown timeout of 3 seconds; a single Ctrl+C
will exit cleanly.

The default host is `127.0.0.1` (loopback only). To accept connections from containers over the
Docker bridge (e.g., for a containerized groom-sidecar inside an agent), pass `--host 0.0.0.0`
and acknowledge the warning. The default port is `8787`. The `/api/state` endpoint returns the
current dashboard state as JSON; its presence and structure are the readiness check.

## Steps

### launch

- kind: service
- run: `uv run groom serve --host 127.0.0.1 --port 8787`
- working-directory: `.`
- timeout: 10
- health: `http: GET /api/state returns 200 with "workflows" in the JSON response body` confirms the server is accepting HTTP requests and serving the dashboard state
- produces: a running Litestar server listening on `127.0.0.1:8787`, accepting HTTP requests and WebSocket connections from the browser dashboard and container sidecars
- verify: [groom server](../http/groom.md)
- provenance: derived

### stop

- kind: drive
- run: `pkill -f "uv run groom serve"`
- working-directory: `.`
- timeout: 5
- verify: [groom CLI serve command](../groom-cli.md#serve)
- optional: true
- provenance: derived

