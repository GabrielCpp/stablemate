---
type: fixture
title: Empty directory
---
# Empty directory

The directory holds no widgets, so [widget-list](../gui/screens/widget-list.md)'s table is
hidden and the empty notice stands in its place.

`api-service` keeps its widgets in process and offers no route that removes one, so the only
arrangement that empties the directory is a fresh process. Restarting the service is therefore
the arrangement itself, not a workaround for a missing one — and it is idempotent, which is
what lets this fixture run after [widgets-on-hand](widgets-on-hand.md) in either order.

- provides:
  - count — the number of widgets the directory holds
    - is: 0

## Steps

### restart-api-service

- kind: run
- run: docker compose restart api-service
- working-directory: `.`

### confirm-it-is-empty

- kind: verify
- run: curl -sf http://localhost:18101/api/widgets | grep -q '"widgets":\[\]'
