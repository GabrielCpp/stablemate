---
type: concept
slug: run-ended-notice
title: Run ended notice
---
# Run ended notice

An operator watching a run, or working in another pane, needs to learn that a run ended. A run the operator has open stays open with a strip that says it ended, how long ago and how, and links to the run in History. The History button on the rail carries a badge that counts the runs that failed since the operator last looked. The screen is the [groom dashboard](../gui/screens/groom-dashboard.md#ended-strip), and the same page holds the [history badge](../gui/screens/groom-dashboard.md#history-badge).

The server says a run ended through one `ended` member on the run's row and on its detail. Its ending comes from the [run ending mapping](run-ending-mapping.md), so the strip, the row, the History table and the [run ending banner](run-ending-banner.md) never disagree about how a run ended.

- code: groom/groom/projection.py::ended_of@bb4def095c60
- code: groom/groom/alerts.py::ingest_spans@e2818cb194ce
- code: groom/groom/app.py::_write_summary@d7fd769a70c0
- code: groom/groom/assets/dashboard.js::EndedStrip@2b1948d89fcb
- code: groom/groom/assets/dashboard.js::noteEndings@258f66db4860
- code: groom/groom/assets/dashboard.js::openInHistory@8d4dc57ff5f1
- rule: a run that has ended carries an `ended` member with its ending, its label, the time it ended, the node it ended at, its error class and whether it failed, on both its row and its detail, so the row, the head and the strip change in the same update
- rule: the ending is read through the run ending mapping and nowhere else, and a run that continues through a reload has no ending and shows no strip
- rule: a run counts as failed when it failed, gave up or crashed, and an interrupted run counts only when its root span recorded `error.kind` as `fatal`, because `interrupt` is the operator's own stop
- rule: a run gave up when the run's fired alerts include `GAVE-UP`, and the strip names it as `gave-up`
- rule: the strip derives from the open run's detail and not from its row, so it stays when the run's row is evicted from the list, and it goes only when the operator selects another run
- rule: the strip's link opens the run in History, clears a kept filter that would hide it, and selects it there once the list has loaded
- rule: when a run's summary is written the server sends every tab a `summary` frame, so an open Overview loads the failure banner and an open History list reloads and shows the run at the top with the totals following
- rule: the last time the operator opened History lives in the browser's local storage, with the ids of the runs that failed since, and the server holds and is told nothing, so the badge costs no server state
- rule: a first load with no last-opened time shows no badge and records now as that time
- rule: opening History clears the badge and records now, and leaving History records now again, so a run that ended while the operator was on History never counts
- rule: a run that ended before the page loaded counts when it failed after the last-opened time, and each run counts once, so a reload does not raise the count
- rule: each badge is hidden from assistive technology and the rail button's accessible name states the count in words, so a count is never colour alone
- rule: the Runs badge counts blocked runs while another pane is open, History included, and the History badge never shows on the History pane
- tests: groom/tests/test_run_ended_dynamic.py::test_a_selected_run_that_ends_stays_open_with_a_strip_saying_it_ended_how_long_ago_and_how
- tests: groom/tests/test_run_ended_dynamic.py::test_the_strip_stays_until_the_operator_selects_another_run
- tests: groom/tests/test_run_ended_dynamic.py::test_a_selected_runs_row_that_is_evicted_leaves_the_detail_open_and_the_list_without_a_row
- tests: groom/tests/test_run_ended_dynamic.py::test_a_run_that_fails_crashes_or_is_stopped_by_a_fatal_error_raises_the_history_badge_by_one_each
- tests: groom/tests/test_run_ended_dynamic.py::test_the_last_opened_time_lives_in_the_browser_and_the_server_is_told_nothing
- tests: groom/tests/test_run_ended.py::test_a_runs_ending_reads_through_the_history_mapping_and_only_a_failure_is_flagged_failed
- tests: groom/tests/test_run_ended.py::test_the_row_and_the_detail_carry_the_same_ending
- tests: groom/tests/test_run_ended.py::test_the_root_span_records_why_the_run_ended_and_a_newer_signal_forgets_it
- tests: groom/tests/test_run_ended.py::test_a_written_summary_is_announced_to_every_tab
