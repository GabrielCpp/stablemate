---
type: concept
slug: run-breakdown-views
title: Run breakdown views
---
# Run breakdown views

The Overview breaks a run's time and cost down in up to three views: by flow, by node and by work item. An operator switches between them and sorts the first two by time or by cost, to see which node or which work item a run's money went to. The views read the same spans as the [run flow tree](run-flow-tree.md), so their totals equal the tree's and the cost tile's, and per-node time equals `groom profile` and `groom cost`.

- code: groom/groom/assets/dashboard.js::Breakdown@e634a482e018
- code: groom/groom/flows.py::node_breakdown@3d65d32d70bb
- code: groom/groom/store.py::run_work_items@9d40b5b83666
- code: groom/groom/norms.py::for_nodes@c2ab9657804d
- code: groom/groom/overview.py::run_overview@d4e666f27ee7
- tests: groom/tests/test_breakdown.py::test_the_median_beside_a_node_counts_successful_runs_only
- tests: groom/tests/test_breakdown_dynamic.py::test_the_view_and_sort_survive_a_tab_round_trip_and_a_live_refresh_and_reset_on_another_run
- tests: groom/tests/test_breakdown.py::test_fewer_than_five_successful_runs_leave_the_comparison_blank_and_the_count_visible
- tests: groom/tests/test_breakdown.py::test_the_table_and_the_strip_read_one_median_from_one_cache
- tests: groom/tests/test_breakdown.py::test_the_item_rows_read_the_laps_groom_loops_counts
- tests: groom/tests/test_breakdown.py::test_items_and_the_outside_row_add_up_to_the_trees_totals
- tests: groom/tests/test_breakdown.py::test_a_run_with_no_work_item_has_no_item_view
- refs: [run flow tree](run-flow-tree.md), [run now strip](run-now-strip.md), [overview tiles](overview-tiles.md), [groom CLI](../groom-cli.md), [get run overview](../http/get-run-overview.md), [the flow table](../gui/screens/groom-dashboard.md#detail-flow-table)

## Views

- rule: the views are By flow, By node and By work item, switched by a button group named `Breakdown view`. By flow is the default.
- rule: By node lists each node once, merged across the flows and states it ran in, with its kind (agent or step), visits, time, mean per visit, longest visit, cost, cost share and retries.
- rule: By node time, cost and visits equal the flow tree's totals and `groom profile`, and a running node's row counts up on the same clock as the tree.
- rule: By work item lists each work item with its passes, agent time, cost and outcome, then a row `outside any work item` and a Total row.
- rule: By work item is offered only when the run has at least one work item. The data decides, not the workflow name, and a run without work items shows no such button.
- rule: By work item reads the same laps as `groom loops` through one shared function, so passes agree with `groom loops` for the same run.
- rule: an item's passes are the most laps any one of its nodes made, and the per-node mix is offered as a tooltip. No node name is fixed in the view.
- rule: an item's time and cost are its agent turns only, and the column says `Agent time`. The `outside any work item` row holds the steps and turns that belong to no item, so items plus outside equal the Total row, which equals the tree and the tiles.
- rule: an item's outcome is derived from the progress count its turns report, because telemetry carries no per-item outcome. It reads done when the run's latest count passed the item's, unknown when the item reports no count, and not counted otherwise. The item with the latest turn of a running run is marked open.

## Median comparison

- rule: the median beside a node is the norm the [run now strip](run-now-strip.md) uses, from the same cache, so the strip and the table show one median for a node.
- rule: the norm counts only successful runs of the same workflow, a run being successful when its root span ended with `workhorse.terminal` equal to `terminal`.
- rule: the comparison needs five such runs. With fewer, the cell stays blank and the heading reads `vs median: N runs, under five`. Otherwise the heading reads `vs median of N`, where N is the sample size from the same read.
- rule: a mean 20% or more above its median reads `+N% longer` in words, and a smaller difference reads dim, so the flag is not colour alone.
- rule: the sample size comes from the cache, not from a scan per update or per sort. A changed cached norm raises the run's `figures_rev`, and an unchanged one does not.

## View and sort state

- rule: the chosen view and sort live in client state on the detail pane. They survive a switch to the Details tab and back and every live refresh, and reset when the operator opens another run. A page reload may reset them.
- rule: both groups expose their pressed state with `aria-pressed` and work from the keyboard.
- rule: By flow and By node sort by time or by cost, and By work item keeps its order of first start and offers no sort.
- rule: the breakdown is fetched with the Overview through the query pool and its coalesced refresh. Sorting happens in the browser and fetches nothing.
- rule: a number on screen agrees with its neighbours at the same moment, so a running node's row counts on the shared clock and the By node totals equal the tree's.
