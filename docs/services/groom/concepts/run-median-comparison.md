---
type: concept
slug: run-median-comparison
title: Run median comparison
---
# Run median comparison

An operator reading History wants to know whether a finished run cost more or less than usual for its workflow. The comparison answers it with the run's cost per finished item against the median cost per finished item of the workflow's successful runs. It appears in four places: a column of the [history table](../gui/screens/groom-dashboard.md#history-table), a cell of the [history totals](run-history-totals.md), the Work items tile of the [overview tiles](overview-tiles.md), and the By node table of the [run breakdown views](run-breakdown-views.md).

The median is read from the stored [history summaries](run-history-summary.md), which cover the store and the [archives](archived-run-history.md), and from nothing else, so the table still opens in under two seconds. A difference is a signed percent in the text of the cell, never a colour alone.

- code: groom/groom/medians.py::per_item_costs@7dc0aa8fbd46
- code: groom/groom/medians.py::median_of_others@4f7dcbfa94de
- code: groom/groom/medians.py::per_workflow@380d64db36ea
- code: groom/groom/medians.py::compare@06ae41aeb33c
- code: groom/groom/medians.py::node_readings@36bf55cc4cc5
- code: groom/groom/history.py::listing@518e84d69d37
- code: groom/groom/history.py::comparison@6a2671c47856
- code: groom/groom/overview.py::run_overview@f1c1a8297756
- code: groom/groom/assets/dashboard.js::historyMedian@b9931eaf950e
- code: groom/groom/assets/dashboard.js::ItemsTile@9c25b8016633
- refs: [run history summary](run-history-summary.md), [run history totals](run-history-totals.md), [overview tiles](overview-tiles.md), [run breakdown views](run-breakdown-views.md), [run now strip](run-now-strip.md), [get run history](../http/get-run-history.md), [get run overview](../http/get-run-overview.md)

## Which runs form the median

- rule: a comparable run is a successful run with a reported cost and a finished item, and every count the screen shows beside a median says comparable, so the operator who reads `26 of 33 ended in success` is not told `3 successful runs` on the same line. A node's count is the comparable runs that ran that node, so it can differ from the workflow's count.
- rule: the median covers every successful run of the workflow whatever the history filters and the range, and the 30-day listing does not limit it. It is taken over every stored summary, so a run frozen into an archive counts in the median and a run's comparison does not move when the range is set to Everything.
- rule: a run enters the median only when it ended in success, has a cost and at least one priced turn, finished at least one item, and is not alive. A run that continued after its summary was written has no end time and stays out.
- rule: a run that reports no cost and shows only an estimate stays out of the median and shows no comparison. Its cost per item reads with the prefix `est`.
- rule: a run priced for only some of its turns stays in the median with the cost it reports.
- rule: the median leaves out the run it is compared with, so a run does not move its own yardstick.
- rule: the comparison needs five other runs. With fewer, the table cell shows the cost per item and no difference.

## What a run shows

- rule: a run that did not end in success shows its cost per item and no comparison, and the tile says the run's ending in words.
- rule: a run with no finished item shows no cost per item.
- rule: a cost per item of ten dollars or more shows whole dollars, and a smaller one shows two decimals.
- rule: a difference is a signed percent with the true minus sign, a plus for more and a minus for less, and the sign carries the meaning without the colour.

## Totals

- rule: with a workflow filter and rows shown, the totals add the median per item of that workflow and the number of comparable runs behind it, which reads `$91 median per coder item, 23 comparable runs`. It leaves out no run, so the number is the whole pool.
- rule: under five comparable runs the totals cell says how many exist and that it takes five, in place of a median. With none it reads `no comparable run yet, and it takes 5`.
- rule: the totals cell and the tile phrase carry the title `Successful runs of this workflow with a reported cost and a finished item`.
- rule: without a workflow filter the totals show no median, because one figure across workflows would compare unlike work.

## Work items tile

- rule: the tile of a compared run reads the cost per item, the signed percent and the number of other comparable runs behind the median, in words.
- rule: under five comparable runs the tile says how many other comparable runs of the workflow exist and that it takes five, and with none it reads `no other comparable run yet`. The word other explains why the tile reads one less than the totals.
- rule: a live run keeps its tile as it was, and only a run that has ended is compared.

## By node

- rule: By node compares an agent node's mean visit time with the median of that node's mean visit times in the other successful runs of the workflow. A step node shows no comparison.
- rule: the heading names the sample size as `vs median of N`, and under five runs it reads `vs median: N runs, under five`.
- rule: a run that did not end in success compares no node, and its heading reads a bare `vs median`.
- rule: the cell of an ended run reads a bare signed percent in plain ink with no word such as longer, so the table agrees with the history column. A run that has not ended keeps `+N% longer` with its warn styling, as the Overview of a live run behaved before.
- rule: the by-node median of an ended run is the median of per-run means, and the [run now strip](run-now-strip.md) keeps its own norm of turn lengths for a live run, so the two figures may differ for a node.
- tests: groom/tests/test_medians.py::test_the_table_cell_shows_cost_per_item_and_the_signed_percent_from_the_median_of_successful_runs
- tests: groom/tests/test_medians.py::test_the_median_leaves_out_the_run_it_is_compared_with
- tests: groom/tests/test_medians.py::test_under_five_comparable_runs_the_cell_shows_the_cost_per_item_with_no_difference
- tests: groom/tests/test_medians.py::test_a_run_that_did_not_end_in_success_shows_its_cost_per_item_and_no_comparison
- tests: groom/tests/test_medians.py::test_a_run_with_no_finished_item_shows_no_cost_per_item
- tests: groom/tests/test_medians.py::test_an_estimate_run_stays_out_of_the_median_and_shows_no_comparison
- tests: groom/tests/test_medians.py::test_a_partly_priced_run_stays_in_the_median
- tests: groom/tests/test_medians.py::test_the_median_covers_every_successful_run_whatever_the_range_and_the_filters
- tests: groom/tests/test_medians.py::test_the_totals_median_is_per_workflow_over_every_successful_run_and_counts_them
- tests: groom/tests/test_medians.py::test_a_run_that_continued_after_its_summary_stays_out_of_the_median
- tests: groom/tests/test_medians.py::test_a_run_still_alive_stays_out_of_the_median
- tests: groom/tests/test_medians.py::test_the_list_with_every_comparison_opens_in_under_two_seconds_and_reads_summaries_only
- tests: groom/tests/test_medians.py::test_an_ended_runs_overview_carries_its_comparison_and_a_run_that_has_not_ended_carries_none
- tests: groom/tests/test_medians.py::test_by_node_reads_each_agent_nodes_mean_against_the_median_of_the_other_successful_runs
- tests: groom/tests/test_medians.py::test_a_failed_runs_overview_compares_no_node_and_names_no_median_size
- tests: groom/tests/test_history_median_dynamic.py::test_the_table_gains_a_column_with_cost_per_item_and_its_signed_percent_from_the_median
- tests: groom/tests/test_history_median_dynamic.py::test_with_a_workflow_filter_the_totals_show_the_median_per_item_and_the_runs_behind_it_without_a_request
- tests: groom/tests/test_history_median_dynamic.py::test_the_work_items_tile_shows_cost_per_item_the_signed_percent_and_the_sample_size_in_words
- tests: groom/tests/test_history_median_dynamic.py::test_by_node_shows_each_agent_nodes_mean_against_its_median_with_the_sample_size_in_the_heading
- tests: groom/tests/test_history_median_dynamic.py::test_the_comparison_surfaces_pass_an_axe_scan_and_carry_the_difference_as_text
