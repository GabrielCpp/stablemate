---
type: concept
slug: dashboard-run-selection
title: Dashboard run selection
---
# Dashboard run selection

Dashboard run selection has one implementation: `select(id)`. A row click and a command-palette
choice both pass their selected run's id to it. The selector first clears the previous detail,
sends the tab's watch subscription, and fetches the selected run's detail. A fetch result applies
only while its selection sequence is current and no pushed detail has arrived first.

Choose the row for a run already visible in the fleet and the command palette for a matching run
from another dashboard pane. This is an input-context choice, not a choice between selection
implementations: both routes use the same selection, subscription, and detail-loading behavior.

- code: groom/groom/assets/dashboard.js::select
- rule: call `select(id)` for every dashboard run selection; choose the row or command-palette entry path by the operator's current context
