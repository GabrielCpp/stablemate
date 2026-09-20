---
type: fixture
title: Widgets on hand
---
# Widgets on hand

The directory holds at least one widget, so [widget-list](../gui/screens/widget-list.md)'s
table has a row to render. The arrangement goes through `api-service`'s own
[post-widgets](../../api-service/http/api-service.md#post-widgets) route rather than reaching
into the store, because the store is in-process and the route is the only way anything outside
the service puts a widget in it — a second way in would be a second thing to keep true.

It starts by bringing `api-service` up rather than assuming a previous scenario left it that
way. An arrangement that depends on the scenario before it having cleaned up is not an
arrangement: run the suite in a different order, or run one scenario alone, and it arranges
nothing. Every fixture here establishes its own precondition for that reason, and
[api-service-unavailable](api-service-unavailable.md) is why it matters in this app.

- provides:
  - name — the seeded widget's name, as it appears in the table's first column
    - from: [seed-one-widget](#seed-one-widget)
    - read: widget.name
  - quantity — the seeded widget's quantity, as it appears in the second
    - from: [seed-one-widget](#seed-one-widget)
    - read: widget.quantity

## Steps

### start-api-service

- kind: run
- run: docker compose up -d --wait api-service
- working-directory: `.`

### seed-one-widget

- kind: seed
- run: curl -sf -X POST http://localhost:18101/api/widgets -H 'content-type: application/json' -d '{"name":"Widget A","quantity":3}'

### confirm-it-landed

- kind: verify
- run: curl -sf http://localhost:18101/api/widgets | grep -q '"Widget A"'
