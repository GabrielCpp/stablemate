---
type: concept
slug: run-now-strip
title: Run now strip
---
# Run now strip

The run now strip sits at the top of the Overview in the detail pane. It answers one question for a live run: is the current turn normal. It shows the node the run is in, how long the turn, step or wait has lasted, how long the agent has been idle and how long ago the last beat arrived. For a turn or a step it also says how that length compares with the norm for the same node.

The norm is the median length of the same kind of work at the same node across the successful runs of the same workflow. It is computed in groom from the telemetry store, cached in memory and read from that cache whenever the strip is built.

- code: groom/groom/norms.py::reading@64f453af5698
- code: groom/groom/store.py::node_norms@7e1e2a873f2a
- code: groom/groom/projection.py::running_strip@f339020e4f63
- code: groom/groom/app.py::_queue_norms@2945bc419aa4
- code: groom/groom/assets/dashboard.js::NowStrip@5e02e693e272
- tests: groom/tests/test_norms.py::test_the_norm_is_the_median_over_successful_runs_of_the_same_workflow
- tests: groom/tests/test_norms.py::test_a_failed_interrupted_or_other_workflow_run_does_not_move_the_norm
- tests: groom/tests/test_norms.py::test_an_agent_node_between_turns_is_not_called_a_step_and_keeps_the_turn_norm
- tests: groom/tests/test_norms.py::test_a_node_never_finished_anywhere_is_neither_a_step_nor_an_agent
- tests: groom/tests/test_breakdown_dynamic.py::test_the_strip_calls_an_agent_node_with_no_turn_gauge_a_node_between_turns_and_agrees_with_the_table
- tests: groom/tests/test_a11y_dynamic.py::test_the_strip_says_a_step_is_longer_than_usual_in_words_and_its_counts_tick
- refs: [run flow tree](run-flow-tree.md), [run telemetry](run-telemetry.md), [the groom dashboard detail pane](../gui/screens/groom-dashboard.md#detail-pane)

## What it shows

- rule: the strip shows the node, the length of the current turn, step or wait, the agent's idle time and the age of the last beat, and a run with no running node shows no strip.
- rule: a turn is the agent working at the node, a step is deterministic work at the node, and a wait is the run held at a gate or other wait. The strip says which in words: `In turn`, `In step`, `Between turns`, `In node`, `Waiting on you` for an operator gate and `Waiting on <kind>` for any other wait.
- rule: a turn or step longer than its norm says `longer than usual` and names the usual length, so the comparison is in words and not in colour alone.
- rule: a turn or step within its norm shows the usual length without the warning.
- rule: a run held at a wait shows the time waited in place of the turn length, says `no norm while waiting` and carries no norm, because a wait is the operator's time and not the node's.
- rule: a step has no agent, so its idle cell says `no agent in a step`.
- rule: the strip decides step or agent from what the node is, not from the absence of a turn gauge. A node is an agent node once any run of the workflow has an agent turn at it, and a step once it has only deterministic work, the same split the By node table's kind column uses.
- rule: an agent node with no turn running reads `Between turns` with the node's running time, and its idle cell says `no turn running`. It names the turn norm in the words `a turn here usually takes`, because the figure is a turn length and the running time is a visit length. It does not say `longer than usual`.
- rule: a node with no finished visit in any run of the workflow reads `In node`, says `no finished visit to compare yet` and carries no median. Its idle cell shows a dash.

## The norm

- rule: the norm is the median of the lengths of a node's agent turns, and a separate median of the lengths of its deterministic step, across the runs of the same workflow that finished successfully.
- rule: a run is one trace, because a run id repeats across executions of the same workflow. A trace is successful when its root span ended with `workhorse.terminal` equal to `terminal`, so a failed, interrupted, reloaded or aborted execution does not feed a norm.
- rule: a node that ran agent turns in a trace contributes those turns and no step sample from that trace.
- rule: under five comparable runs the strip says `no norm yet` and the run count, and shows no median.
- rule: a run of another workflow does not feed the norm, even at a node of the same name.

## Reads

- rule: the norm is cached in memory per workflow and node, and building the strip reads only the cache, so a pushed detail frame, a received telemetry batch and a render read nothing from the store.
- rule: the cache fills through the store's query pool, off the event loop and off any timer, once per workflow and node when a watched run first reports the node and again when the run moves to a new node. It does not scan the whole store on an update.
- rule: the By node table of the [run breakdown views](run-breakdown-views.md) reads the same cache and the same five-run minimum, so the strip and the table show one median for one node.
- rule: while the first read is outstanding the strip says `reading the norm`, and the detail is pushed again when the read lands.

## Counting

- rule: the turn length, the agent idle time and the age of the last beat count up every second in the browser from server timestamps, with no reload, no read and no server frame.
- rule: each count is a timestamp the server derives from the newest elapsed gauge and the time that gauge arrived, so a count the producer stopped reporting keeps growing from where it was rather than freezing.
- rule: the strip, the run list row's line and the flow tree's running mark and Time cell share one clock. The server sends one start timestamp for the turn, the node and the wait, derived once from the arrival time of the elapsed gauge, and each surface counts up from it, so the same turn reads the same length on all of them at the same moment.
- rule: every surface that counts ticks from one shared one-second timer in the browser, so they change together. A tick re-renders only the small text each surface owns, not the run list or the tree, and reads nothing from the store.
- rule: the tree's running mark counts the node and the strip counts the turn. They read the same length for a node's first turn and differ once the node has run an earlier turn.
- rule: the strip is a labelled group, `Where the run is now`, and does not announce itself to a screen reader as it counts.
