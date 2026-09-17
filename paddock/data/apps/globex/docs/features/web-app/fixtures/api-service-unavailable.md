---
type: fixture
title: api-service unavailable
---
# api-service unavailable

The read [widget-list](../gui/screens/widget-list.md) makes from the browser fails, so the page
shows its alert instead of a table or an empty notice. The browser is the only thing that talks
to both services, so taking `api-service` down is what a failed read looks like from `web-app`'s
side — nothing on `web-app` needs to be touched, and nothing pretends the failure came from
somewhere it did not.

This fixture leaves the stack altered on purpose and does not put it back. That is safe here
only because every other fixture in this directory starts by bringing `api-service` up itself
rather than trusting a teardown to have run.

- provides:
  - reason — why the directory read fails, which is that `api-service` is not listening

## Steps

### stop-api-service

- kind: run
- run: docker compose stop api-service

### confirm-it-is-down

- kind: verify
- run: sh -c '! curl -sf --max-time 2 http://localhost:18101/healthz'
