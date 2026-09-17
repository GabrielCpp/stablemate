---
type: environment
slug: local
title: Local
---
# Local

The one environment this fixture defines. It stands up both services from a single
`docker compose` project so a reader (or a runbook) can bring up the whole stack, or either
half of it, from one file. This is the fixture's only environment with two `services:`
children — every other app under `paddock/data/apps/` has one service per environment, so
this node is the first place a service-to-service link inside `services:` is exercised
rather than left as unlinked prose.

- selector: local-only — the fixture has no staging or production target
- services:
  - api-service: [http://localhost:18101](../http/api-service.md)
  - web-app: [http://localhost:18102](../../web-app/gui/screens/widget-list.md)
- backing:
  - none — widgets live in an in-process store, reset on restart
- local-only: true
- code: `compose.yml` @69d0b0918e8a
- config: `STABLEMATE_API_BASE` is not read by either service; web-app's browser client
  reads its API origin from `app/web-app/static/config.js`, not from process environment,
  because the fetch is made by the page, not by the web-app process.
- tests:
- fixture: `docker compose up --build`
- capture:
- persistence: widget — a widget created before a restart of this environment does not
  survive it (the store is in-process and reinitializes empty on the next `docker compose up`)
- verify: absent(subject="a widget created before `docker compose restart api-service`, read back after")
