---
type: concept
slug: run-row-figures
title: Run row figures
---
# Run row figures

Every run row in the list carries three figures beside the run's name and state: the cost so far with its coverage, the active time, and the items done out of the total. An operator scanning the fleet reads which run is spending without opening each one, and the narrowed column beside an open detail keeps the same figures.

The figures live in the run's hot-cache record as `figures`. The list renders only what the record already holds, so drawing the list reads nothing from the telemetry store. A recompute of one run's figures is queued after a span batch for that run commits, and it calls the same store functions that `groom cost` and `groom profile` call, so a row cannot drift from either report.

- code: groom/groom/figures.py::run_figures@193e82e6604e
- code: groom/groom/store.py::latest_progress@69b8f1f7ef1f
- code: groom/groom/store.py::active_seconds@7bf6c0eb3fdc
- code: groom/groom/app.py::_refresh_figures@655a796ee0d1
- code: groom/groom/assets/dashboard.js::RowFigures@3c877ee5e531
- tests: groom/tests/test_row_figures.py::test_the_figures_match_the_terminal_reports
- tests: groom/tests/test_row_figures.py::test_items_come_from_the_latest_ended_span_with_a_count
- tests: groom/tests/test_row_figures.py::test_refreshes_coalesce_to_one_running_and_one_rerun
- tests: groom/tests/test_row_figures.py::test_the_row_carries_the_cached_figures_and_the_order_is_unchanged
- refs: [runs fleet view](../runs-fleet-view.md), [run telemetry](run-telemetry.md), [run flow tree](run-flow-tree.md), [groom store](groom-store.md), [groom CLI](../groom-cli.md), [run row](../gui/screens/groom-dashboard.md#run-row)

## Items

- rule: a row's items figure is the `progress` attribute on the run's most recently ended span that carries a value of the form `done/total`, read by end time. Each workflow reports it from its own `labels()`, so the numerator is finished items and the denominator is the total.
- rule: a `progress` value that is not two whole numbers around a slash is prose and does not count as an item figure, even when the span is newer than the last count.
- rule: a total of zero, as in `0/0` before any story is filed, is not a count. The row shows no item figure until a span reports a positive total.
- rule: the row prints `8/30 items`. Telemetry carries no noun for the work, so the row names no kind of item.
- rule: a run that reports no such value shows no item figure and no placeholder that implies a count.
- rule: items done, the item total and the finished items that a cost per item divides by all come from this one figure.

## Active time

- rule: a row's active time is the agent, deterministic and infrastructure seconds of the profile's time partition. Waits, resume gaps and unclassified time are not active.
- rule: `groom profile` prints the same figure on its own `active=` line, so a row's active time is checked by reading that line.
- rule: the Overview tree's Time column is not reconciled with active time. The tree sums each row's own time, and work that overlaps in time can make that sum differ from the active figure.

## Reaching the row

- rule: figures are recomputed for one run through the query pool, with the store functions behind `groom cost` and `groom profile`, after a span batch for that run commits. The hot cache holds no incremental ledger, because a ledger would repeat the per-turn charge logic and could drift from `groom cost`.
- rule: at most one recompute runs per run. A batch that arrives while one runs marks the run dirty and queues one rerun behind it, however many batches arrive.
- rule: after a groom restart the hot cache holds no figures, so a run's first sight in any telemetry batch computes them once. A later metric or log batch does not recompute them.
- rule: nothing recomputes on a timer, and rendering the list and the clock tick leave the store unread.
- rule: a recompute that fails leaves the previous figures on the row and is tried again at the next span batch.
- rule: figures leave a row's rank unchanged or the list order. The order stays blocked, then alive, then presumed dead, then finished, with ties broken by name.

## Reading the row

- rule: the cost carries its coverage as priced turns out of total turns. The wide list shows the word `priced` and the narrowed column omits it.
- rule: a backend that reports no cost shows the words `no cost reported` in place of a dollar figure.
- rule: a run with no finished node shows `no cost yet` in place of a dollar figure, and gets its figure once its first node finishes.
- rule: a row with no figures yet, because the first read has not returned, shows no figures line at all.
