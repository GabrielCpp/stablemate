---
type: concept
slug: run-history-summary
title: Run history summary
---
# Run history summary

History answers what a run cost, how long it took and how it ended after the run has left the fleet. It cannot answer by scanning a run's records, because the store holds the records of every run for 30 days and a scan per run would not open in seconds. Groom therefore keeps one stored summary row per ended run and the list reads only those rows. The row holds the workflow, repo, branch, run folder, native or container, the [ending](run-ending-mapping.md), the error class and failing node, the resume command the run recorded at launch and whether it ran in a container, the start, end and last-record times, the active and wall time, the cost with its priced and total turns and its estimate, the items finished and total, the turns, gates and problems, the sessions with how each stopped, and the per-node visits, time and cost.

A run is listed only once it has ended. The repo and branch come from what the run's spans record, the same way the Runs pane names them. The repo is the one the spans declare, or the directory name of the workspace path they record, and the branch is the one they declare or the branch they record at the start. A run whose spans record no workspace has no repo and the table shows a dash. The stored repo and branch are the plain name and the plain branch, separately, and the table joins them with `@`.

A run that is alive, which is a run the server holds with no terminal and heard from recently, is not listed, and a run that continues after a resume leaves the list while it is alive and returns with its new figures when it ends again. A finished run is listed even while its row is still in the Runs pane. A run that was never given an ending is listed once it has been silent for 48 hours, and it leaves the list if it comes back alive.

A background worker on a pool of its own writes the summary of an ended run that has none, one run at a time, and wakes when an end is heard and on a timer. Until the worker has written the row, the list shows the run by its run, repo and end time and says the summary is being read. The dashboard asks again every four seconds while any row is pending, so the row fills in without a reload. The list and the worker never share a pool, so a page read is not queued behind a summary.

A run whose rows have left the store for an [archive](archived-run-history.md) keeps its row, flagged archived, so History can still list it.

The operator-facing screen is the [history table](../gui/screens/groom-dashboard.md#history-table), and its figures above the table are the [run history totals](run-history-totals.md). The route is [get-run-history](../http/get-run-history.md).

- code: groom/groom/history.py::discover@1c90072aa772
- code: groom/groom/history.py::compute@afbde2532938
- code: groom/groom/history.py::listing@518e84d69d37
- code: groom/groom/app.py::_summary_loop@7d25526428f4
- code: groom/groom/pools.py::SUMMARY@9f14083a924c
- rule: the resume command is read from the run's launch record when its summary is written, as `cd <recorded cwd> && <resume argv>` with shell quoting, and an ended run summarized before the record was read, or with an older form of the command, is summarized once more so its row gains it. The [run ending banner](run-ending-banner.md) shows it.
- rule: a run that gave up stores the node of its give-up span as its failing node
- rule: the history list reads stored per-run summaries and scans no run's records
- rule: a run that is alive is not listed, a finished run is listed while its row is still in Runs, and a run that continues after a resume leaves the list and returns with its new figures when it ends again
- rule: a run with no recorded ending is listed after 48 hours of silence at its last record's time, and leaves the list if it comes back alive
- rule: the repo is the one a run's spans declare or the directory name of the workspace path they record, the branch is the one they declare or record at the start, and both are stored plain and separately, so a run reads the same repo and branch in History as in Runs
- rule: a run whose spans record no workspace reads no repo, and the pending row carries the same repo and branch as the summary that replaces it
- rule: a long run name or repo cuts off with an ellipsis at 230 px and keeps its full text as the cell title, so every column of the table stays in view
- rule: a summary is written by a background worker with one thread on a pool of its own, one run at a time, so a page read never waits for it
- rule: an ended run with no summary yet is listed by run, repo and end time as being read, and is left out of every sum
- rule: each row carries its cost per finished item and its comparison with the [median of the workflow's successful runs](run-median-comparison.md), computed from the stored summaries alone
- rule: the list holds the runs that ended in the last 30 days, the same retention as the telemetry store, newest end time first, and with the range set to Everything it also holds every [archived run](archived-run-history.md) whatever its age
- rule: a summary row carries a flag that says it describes an archived run, and an archive whose summary cannot be read keeps its row with no figures and the state unreadable
- verify: json_path(path="$.totals.runs", matches="^[0-9]+$")
- tests: groom/tests/test_history.py::test_a_run_whose_spans_name_a_workspace_and_a_branch_reads_that_repo_and_branch
- tests: groom/tests/test_history.py::test_a_run_whose_spans_record_no_workspace_keeps_no_repo
- tests: groom/tests/test_history.py::test_a_live_row_and_history_label_one_run_with_the_same_repo_and_branch
- tests: groom/tests/test_history.py::test_the_list_reads_summaries_and_opens_in_under_two_seconds_with_the_store_full
- tests: groom/tests/test_history.py::test_the_summary_worker_has_a_pool_of_its_own_with_one_thread
- tests: groom/tests/test_history.py::test_a_summary_pass_writes_the_rows_that_are_missing_one_run_at_a_time
- tests: groom/tests/test_history.py::test_an_ended_run_with_no_summary_yet_is_listed_unread_and_fills_in_when_it_is_written
