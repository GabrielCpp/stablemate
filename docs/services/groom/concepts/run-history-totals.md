---
type: concept
slug: run-history-totals
title: Run history totals
---
# Run history totals

The strip above the history table gives the operator the answer to what the listed runs cost before reading a row: the number of runs, the money spent, the active time, and how many ended in success. Money counts the reported cost of every run that has one and the estimate of a run that reports none, because a backend that reports no cost would otherwise make the spend read lower than it was. The strip says how much of the money is an estimate and how many runs are partly priced, which is a run whose reported cost covers only some of its turns, so the operator can judge how far to trust the figure.

A run whose summary is still being read counts in the number of runs and adds nothing to the sums or to the success count, and the strip says how many are being read. The success count reads against the runs whose summary is ready, not against all runs.

- code: groom/groom/history.py::totals@4a99a0e9f8a4
- code: groom/groom/assets/dashboard.js::historyTotals@d98d0ba7b1bd
- code: groom/groom/assets/dashboard.js::historySums@d98874013e39
- rule: the money spent is the reported cost plus the estimate of the runs that report no cost
- rule: the strip says how much of the money is an estimate and how many runs are partly priced, and omits each clause when it is zero
- rule: a run still being read counts in the number of runs and stays out of the sums and the success count
- rule: the success count reads against the runs whose summary is ready
- rule: the strip describes the rows shown after the [history filters](run-history-filters.md), and the browser sums them the way the route does
- rule: a row shows the reported cost with the priced count beside it when some turns reported none, and the estimate with the prefix est when the backend reports no cost
- tests: groom/tests/test_history.py::test_the_totals_count_runs_money_active_time_and_successes
- tests: groom/tests/test_history.py::test_a_run_still_being_read_counts_in_runs_and_stays_out_of_the_sums_and_the_success_count
- tests: groom/tests/test_history.py::test_an_empty_history_totals_zero
- tests: groom/tests/test_history.py::test_a_backend_that_reports_no_cost_shows_an_estimate_and_no_cost
