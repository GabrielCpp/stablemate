story: SM-01M6CN5ZS6SQNVMD97SY4HM4ZR
date: 2026-11-23
elements: RunDetail
sources: groom/groom/flows.py, groom/groom/norms.py, groom/groom/store.py, groom/groom/overview.py, groom/groom/assets/dashboard.js

The operator wanted to trace a high cost to one node against its median, or to one work item. The Overview holds one
time and cost table with a switch above it: By flow, By node and By work item.

By flow is the default. By work item exists only for a run whose turns carry a work item, so a run without items
offers two views and the overview's `items` is null.

By node merges the flow tree's leaf rows by node across flows and states. A node reached from two states is one row,
and the rows add up to the tree. The times equal the leaves of the tree `groom profile` prints, because both read the
same stored tree. A node's kind is agent, step or none. Its mean is its time over its samples: the agent turns of an
agent node, the visits of a step.

The median comes from the norm cache the run strip reads. It covers successful runs of the same workflow only and
needs five of them, as `the-strip-compares-a-turn-with-its-nodes-norm` settled. Under five runs the cells stay blank
and the heading names the count and "under five". On a live run a mean 20% or more above the median reads "longer" in
words beside the warning color.

Passes are the most turns any one node took for the item, the per-node laps `groom loops` counts, so an item that went
through build once and review once shows one pass. A short label beside the count names the node with the most laps. Time
is the agent time of all the item's turns across its nodes. An "outside any work item" row and a Total make the rows add
up to the tree. The open item is the item touched last while the run is live.

An item's outcome is derived from the run's progress count. It reads done when the count moved past the item's count,
and not counted otherwise. It is blank when no count was reported. This is a guess, because telemetry carries no
per-item outcome. An outcome attribute emitted by the workflow would remove the guess, and that work belongs to the
workflows.

Sorting is by time or by cost. It ranks by output tokens when the backend reports no cost. It runs in the browser with
no request, and By work item keeps its own order.

The view and sort belong to the page's selection of a run. A trip to another tab and back and a live refresh keep
them, and selecting another run resets them to By flow and Time. The story named the Details tab. That tab gave way to
Activity under `the-details-tab-gave-way-to-activity-files-and-diff`, so the round trip goes through Activity.
