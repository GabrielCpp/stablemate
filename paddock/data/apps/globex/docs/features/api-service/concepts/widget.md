---
type: concept
slug: widget
title: Widget
---
# Widget

The one domain record this fixture ships: a name and a quantity on hand. A widget has no
lifecycle beyond being created — no edit, no delete, no status — because the fixture's job
is exercising a two-service stack and its flows, not a rich domain model.

A widget's identity is a generated id (`wg-a`, `wg-b`, …), assigned in creation order; the
name is not the identity and is not required to be unique.

- code: `app/api-service/store.go::Widget` @6e2b9b344f38
- rule: a widget is accepted only with a non-empty `name` and a `quantity` of zero or more;
  either violation is refused rather than coerced (a blank name kept as blank, a negative
  quantity clamped to zero).
- tests: `app/api-service/store.go::Store.Create`
