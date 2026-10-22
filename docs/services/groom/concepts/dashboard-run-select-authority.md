---
type: concept
slug: dashboard-run-select-authority
title: Dashboard run select authority
---
# Dashboard run select authority

The dashboard has one run-selection implementation, `select(id)`, documented by two concept
nodes at different depths: [dashboard run selection](dashboard-run-selection.md) states the
entry-path rule (row click vs command-palette choice) and summarizes the selection, watch, and
detail-loading behavior in a paragraph; [dashboard run selector](dashboard-run-selector.md) is
the full contract — every store write, the watch subscription, the detail-fetch race rules, the
accessibility contract, and the `select` method's algorithm, step by step.

These are not competing implementations to choose between; the code has exactly one. The two
docs exist at different zoom levels of the same thing, and a reader who needs anything beyond
the entry-path rule — a store-write guarantee, a race condition, an accessibility attribute —
has to leave the short one and read the full contract.

- rule: read [dashboard run selector](dashboard-run-selector.md) for the selector's full
  contract; [dashboard run selection](dashboard-run-selection.md) states only the entry-path
  choice and defers to the selector for everything else
- prefers: [dashboard run selector](dashboard-run-selector.md)
