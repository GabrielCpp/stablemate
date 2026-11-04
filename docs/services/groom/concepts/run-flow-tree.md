---
type: concept
slug: run-flow-tree
title: Run flow tree
---
# Run flow tree

The run flow tree is the Overview tab's account of where a run's time and money went: a tree of flow, state and node, each row carrying visits, time, cost and retries. It is built by one pure function over the run's stored spans, so the Overview, `groom profile` and the profile JSON read the same rows. Cost and per-node time agree with `groom cost` and `groom profile` for the same run, because the tree sums the same per-turn charges and durations those commands do.

Spans export when they end. A flow or state that is still open, and the run's own root span, are absent from the store. The tree places finished work by walking the parents that did end. Where the walk meets a parent that is missing, it reads the flow and state names the work's own span carries, which workhorse stamps on every step of a new run. A new run therefore names its open flow while it runs. A run recorded without those names shows the work as unfinished. The tree never names a parent it cannot read from a span.

- code: groom/groom/flows.py::build_flows@3c6e64500c11
- code: groom/groom/overview.py::run_overview@f1c1a8297756
- code: groom/groom/live_history.py::LiveHistory@3671ced6241f
- code: groom/groom/assets/dashboard.js::Overview@a13d033913fa
- code: groom/groom/flows.py::turn_passes@74192984c983
- code: groom/groom/flows.py::span_passes@55f223c1146d
- tests: groom/tests/test_flows.py::test_an_ended_flow_is_named_from_its_own_span
- tests: groom/tests/test_flows.py::test_work_under_an_unexported_parent_gets_one_unfinished_row_per_parent
- tests: groom/tests/test_flows.py::test_work_in_an_open_flow_is_named_from_its_own_attributes
- tests: groom/tests/test_flows.py::test_dropping_the_flow_and_state_spans_of_a_finished_run_changes_no_row
- tests: groom/tests/test_a11y_dynamic.py::test_the_time_cell_carries_a_proportional_bar_beside_the_duration
- tests: groom/tests/test_a11y_dynamic.py::test_new_telemetry_updates_the_open_overview_and_keeps_the_operators_place
- tests: groom/tests/test_a11y_dynamic.py::test_the_time_since_the_last_finished_turn_counts_up_every_second
- tests: groom/tests/test_live_history.py::test_only_a_span_batch_advances_the_figures_revision
- tests: groom/tests/test_activity.py::test_a_turn_is_numbered_by_the_runs_of_its_flow_node
- refs: [overview tiles](overview-tiles.md), [run breakdown views](run-breakdown-views.md), [groom store](groom-store.md), [groom projection module](groom-projection-module.md), [groom CLI](../groom-cli.md), [get run overview](../http/get-run-overview.md), [the groom dashboard detail pane](../gui/screens/groom-dashboard.md#detail-pane)

## Rows

- rule: a row is one of four kinds: `flow` (a node-kind span that has state or node spans beneath it), `state` (a span with `workhorse.span_kind` equal to `state`), `node` (any other span that is not a run root, an agent turn or an infrastructure span), and the two bucket rows `workflow` and `unfinished`.
- rule: a node's work is its leaf spans plus the agent turns attached to it; a span that parents a state or node span is a container, not counted as work itself.
- rule: a node row's time is the sum of its agent turns' profile durations, and the span's own duration only when it has no turns, so the figure matches `groom cost` and `groom profile` minute for minute.
- rule: a node row's visits are its node spans plus the turn groups whose node span did not end; a flow row's visits are its distinct ended flow spans, blank when none has ended; the `workflow` and `unfinished` rows carry no visit count.
- rule: a node row's retries are its agent turns minus its distinct turn groups, one group per node-span visit, so a node that ran once and was retried twice shows 2.
- rule: a state span that holds no child span except infra spans is a step of its own. Its seconds count as time in its flow, its state and its node, whether it passed or failed, and the Overview's By flow and By node tables show it. It has no agent turn, so its cost stays empty and is not shown as `$0`. Its visits count as for any node, and a state that holds a node or another state adds nothing, because that work already counts once.
- rule: a state with exactly one node renders as one row, labelled with the state name when the node has the same name and otherwise `state › node`.
- rule: the Time column sums each row's own time and is not reconciled with a run's active time. Work that overlaps in time can make the tree's total differ from the active figure that [run row figures](run-row-figures.md) and `groom profile` print.
- rule: rows sort by time descending, then by name, or by cost when the operator picks that sort, at every depth; a parent's figures are the sums of its children.
- rule: a row's cost is the sum of its priced turns and is absent when none of its turns is priced; an absent cost is not shown as `$0` nor as a blank.
- rule: when a run reports no cost at all, the tree shows each row's output tokens in place of cost.
- rule: the same rows feed the [run breakdown views](run-breakdown-views.md): each leaf row also carries its node name, visit samples and longest visit, and By node merges them by node.
- rule: the Overview's "as of" time is the end of the last finished agent turn, so the cost it shows reads "as of the last finished turn" and does not claim to include a turn still running.

## Placement

- rule: placement walks span parents first. A flow is the nearest ended node-kind ancestor above the work's state, or the nearest ended node-kind ancestor when the work has no state. A state is the nearest ended state at or above the work. Old runs depend on this walk, so it is read first.
- rule: where the walk stops at a parent that has not exported, the work's own `workhorse.flow` and `workhorse.state` attributes name its flow and state. A named flow is the flow row of that name, whether or not its span has ended, so a flow keeps one row when it ends between two reads.
- rule: a present but empty `workhorse.flow` places the work under the run's workflow row, and a named state sits under that row. A state at depth 0 sits under the run's own workflow row, named by the run's workflow.
- rule: work whose span carries no `workhorse.flow` attribute and whose walk stops at a missing parent sits under a row labelled exactly `Unfinished flow or state`, with one such row per missing parent id. Two missing parents make two rows. The label carries no guessed name, and the missing parent's id is offered only as a tooltip on the row.
- rule: finished work with no parent span and a depth other than 0 is treated as having a missing parent, and goes through the same rule.
- rule: a flow or state that is open has no ended span, so its visit count is blank, not 0. It carries no unfinished label.
- rule: the running node is a top-level row of its own, marked in words, because its own span has not exported. It is not placed under a guessed flow or under an unfinished row.
- rule: a run recorded before spans carried the names still shows its flows, because the walk reads only the span parent links and depth attribute every earlier run already carries.

## Running and waiting marks

- rule: the running row reads `running` with the node's running time. A node held at a wait reads `waiting on the operator` with the time waited when the wait is an operator gate, and `waiting on <kind>` for any other wait. A waiting node is not marked running.
- rule: the marks are words, not colour alone.
- rule: the running row's mark and Time cell count up every second from the server's start timestamp for the node or wait, the same clock the [run now strip](run-now-strip.md) and the run list row use.

## Time cell

- rule: every row's Time cell shows the duration with a thin bar beside it. The bar's width is the row's time as a share of the run's total time, clamped between 1% and 100%.
- rule: the bar is decoration for sighted readers and is hidden from assistive technology, because the Time % column already says the share in words.

## Live refresh

- rule: an open Overview refetches its figures when the run's watched history absorbs a committed span batch, because spans and agent turns are the only telemetry that moves cost, coverage or the tree. A log batch or a metric batch does not refetch.
- rule: the server tells the pane which batch it is on with `figures_rev` in the run detail, a count that rises once per committed span batch while at least one tab has the run open. The pane refetches when the count differs from the one its figures were read at.
- rule: `figures_rev` also rises when a cached node norm changes, so a median beside a node refreshes without a span batch.
- rule: nothing refetches on a timer. A run with no new span batch causes no read, and a run with no open detail keeps no history and so reads nothing when its telemetry arrives.
- rule: a refetch replaces the figures in place. The Overview stays out of its loading state, keeps every figure visible, keeps every row as it was and keeps the scroll position, because the same rows stay mounted and only their values change.
- rule: a refetch that fails leaves the figures on screen as they were and tries again at the next span batch. Only the first read of an Overview shows the failure message.
- rule: the expanded rows are the operator's and survive every refresh. A flow that first appears in a refresh starts collapsed.
- rule: the running mark follows the pushed run detail, not the refetch, so a node that finishes loses it and the next running node gains it as soon as the run reports the change.
- rule: the [run now strip](run-now-strip.md) sits above the [overview tiles](overview-tiles.md) and the tree, and a refetch of the figures leaves it untouched.
- rule: the cost tile's "ago" and the attention tile's waiting time tick every second in the browser from the last finished turn's end time, with no read and no server frame. The figures do not announce themselves to a screen reader as they change.

## Turn passes

- rule: a turn's pass is which run of its flow's node span it belongs to, counted from one in the order those runs started. The [Activity tab](run-activity-tab.md) shows it as `1st pass`. A turn outside any flow node has no pass. The Activity tab places a step, a gate and a turn in a pass by the same walk up the spans, numbers the passes within a work item and flow, and a pass still open is named by its span's flow attribute and numbered after the stored passes.

## Cost coverage

- rule: the Overview states cost beside its coverage: priced turns out of total turns.
- rule: a backend that reports no cost says so in words. The Overview shows no dollar figure for it, and shows an estimate only as `est $X at list price`, labelled as an estimate.
- rule: a run with no finished node says figures appear when the first node finishes, shows its running node, and shows no cost figure.

## Reads

- rule: selecting a run reads that run's spans only, through one indexed query, not the whole telemetry store.
- rule: the Overview loads on its own, shows a loading state that clears, and on a failed read shows a message with a retry; the Activity tab keeps working while it is failed, and the message clears on the next successful read.
