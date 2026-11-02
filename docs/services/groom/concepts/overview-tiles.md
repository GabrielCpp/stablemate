---
type: concept
slug: overview-tiles
title: Overview tiles
---
# Overview tiles

Five tiles sit at the top of a run's Overview: Cost, Active time, Work items, Agent turns and Attention. An operator reads what the run has spent, how long it has really worked, how much of it is done, how often the backend had to retry and what is waiting on a person, without opening the flow tree.

The tiles are not a second set of numbers. Cost, coverage, active time and items come from the figures module that feeds the [run row figures](run-row-figures.md), so a tile and its run row read the same at the same moment. The retries and the problem count come from the one store read that builds the [run flow tree](run-flow-tree.md), so the tile's retries are the sum of the tree's Retries column.

- code: groom/groom/figures.py::tile_figures@56086656f4a0
- code: groom/groom/problems.py::standing@2c9cd56a1366
- code: groom/groom/churn.py::count_alerts@156655db35bb
- code: groom/groom/overview.py::run_overview@d4e666f27ee7
- code: groom/groom/assets/dashboard.js::OverviewTiles@1e3959a72410
- tests: groom/tests/test_overview_tiles.py::test_the_problem_count_adds_failed_steps_retries_failed_gate_checks_and_churn
- tests: groom/tests/test_overview_tiles.py::test_an_answered_gate_is_counted_as_a_gate_and_not_as_a_problem
- tests: groom/tests/test_overview_tiles.py::test_the_retries_on_the_tile_equal_the_sum_of_the_trees_retries_column
- tests: groom/tests/test_overview_tiles.py::test_churn_is_derived_from_stored_spans_and_holds_with_no_hot_cache
- tests: groom/tests/test_overview_tiles.py::test_the_derived_churn_count_matches_the_alert_rule_over_the_same_spans
- tests: groom/tests/test_overview_tiles.py::test_the_tile_figures_are_the_run_rows_figures
- tests: groom/tests/test_a11y_dynamic.py::test_the_five_tiles_read_the_runs_standing
- tests: groom/tests/test_a11y_dynamic.py::test_the_attention_tile_waits_as_long_as_the_tree_says
- tests: groom/tests/test_a11y_dynamic.py::test_a_run_with_no_finished_node_shows_no_tiles_and_no_problem_count
- tests: groom/tests/test_a11y_dynamic.py::test_a_backend_with_no_cost_labels_its_estimate_and_gives_no_cost_per_item
- tests: groom/tests/test_a11y_dynamic.py::test_the_tiles_refresh_in_place_when_a_turn_lands
- refs: [run clock sections](run-clock-sections.md), [run flow tree](run-flow-tree.md), [run row figures](run-row-figures.md), [run now strip](run-now-strip.md), [get run overview](../http/get-run-overview.md), [the groom dashboard detail pane](../gui/screens/groom-dashboard.md#detail-pane)

## Figures

- rule: the Cost tile shows the cost so far, `as of the last finished turn` with its age, the priced turns out of the total, and a burn rate in dollars per active hour. The burn rate is the tile's cost divided by the Active time tile's active time in hours, and is absent while active time is zero.
- rule: a run whose backend reports no cost shows no dollar figure on the Cost tile. It shows the backend's name with `reports no cost` and, when the rate card prices the tokens, `est $X at list price`. An estimate carries that label.
- rule: the Active time tile shows the active time and, beside it, the wall time and the session count, as `<wall> wall, N sessions`. Wall time appears beside active time.
- rule: a session is one distinct resume generation among the run's spans. A run whose spans carry none is one session. The Sessions table in the [run clock sections](run-clock-sections.md) lists exactly these sessions.
- rule: the Work items tile shows `N of M` items done from the same figure as the run row, and the cost per finished item, which is the run's cost divided by the items done.
- rule: while no item has finished the tile says `none finished yet` and shows no per-item figure. A run with no cost shows `no cost per item without a price`, and a run that reports no item count shows `no item count reported`.
- rule: the Agent turns tile shows the turn count and the backend retries, and the retries equal the sum of the flow tree's Retries column because both read the same computation.

## Attention

- rule: the Attention tile shows the gates, the time spent waiting on them and the problem count.
- rule: a gate is an operator wait span. An answered gate counts as a gate and contributes its waited time. It does not count as a problem.
- rule: the gate still open counts as one gate, and its wait counts up every second in the browser from the same start time as the tree's waiting mark and the run now strip, so the three read the same at the same moment.
- rule: problems are the sum of four counts: failed steps, backend retries, failed gate checks and churn alerts. The count is at least the retries.
- rule: a failed step is an errored span that is not a run's root span and does not parent another errored span, so one failure counts once however deep it sits.
- rule: a failed gate check is a span that carries a gate outcome whose status is dirty.
- rule: a churn alert is the same node completing again under an unchanged label signature, repeated `GROOM_CHURN_REPEATS` times, the rule the live churn alert uses. A changed label is progress and ends the run of repeats. A new resume generation starts the count again.
- rule: the problem count is derived from the run's stored spans, so it holds after groom restarts and for a run no browser has opened.
- rule: the tile's hover text lists the four counts that make the problem count.

## Refresh

- rule: the tiles are computed on the query pool by the same read as the Overview, refetched when a span batch commits, not on render and not on a timer.
- rule: a refetch replaces the tiles in place and keeps the scroll position and the expanded rows.
- rule: a run with no finished node shows no tiles, no problem count and none of the wall clock, Models and Sessions sections of the [run clock sections](run-clock-sections.md), only the message that figures appear when the first node finishes and the Run facts list.
