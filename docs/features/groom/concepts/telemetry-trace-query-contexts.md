---
type: concept
slug: telemetry-trace-query-contexts
title: Telemetry trace query contexts
---
# Telemetry trace query contexts

The dashboard uses the same telemetry query and rendering path in two current contexts. Entering
Telemetry mode calls the trace loader so the pane shows results immediately. While that pane is
active, input, change, and submitted-form events call the loader again with the form's current
values so the results reflect the operator's filter.

Neither context supersedes the other: mode selection establishes the telemetry view, while form
events refine or refresh the already-selected view. `loadTraces` serializes the form and replaces
the trace slice; `Traces` renders that slice for either caller.

- code: groom/groom/assets/dashboard.js::loadTraces
- code: groom/groom/assets/dashboard.js::Traces
- rule: select Telemetry mode to load the telemetry view; use the telemetry filter form to re-query that selected view with its current filter values; neither invocation is ranked over the other
