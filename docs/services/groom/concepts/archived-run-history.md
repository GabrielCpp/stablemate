---
type: concept
slug: archived-run-history
title: archived run history
---
# archived run history

An operator who wants to look back at a run that left the thirty-day window chooses Everything in the History range and finds that run listed with its figures, then opens it and reads its Overview. The run's rows left the telemetry store when [the archive](groom-archive-module.md) froze it, so the list cannot be built from the store, and the Overview cannot be built from a scan of the table either.

A summary of the run is computed once, while the run still has its rows, and the archive's manifest carries it. Groom copies it into the one [stored summary](run-history-summary.md) table with the flag `archived`, so the list reads the same rows for an archived run as for a run still in the store. An archive frozen before summaries existed has a manifest with no summary. Groom lists it at once from its folder name and manifest, says its summary is being read, and a background read on a pool of its own fills the row in, once, without a reload. The frozen file is never rewritten.

The Overview of an archived run is read from the frozen file through the same terminal queries as a live run, so its cost and times per node and flow equal `groom cost` and `groom profile`. The first open of an archive builds an index beside the file, which takes a few seconds, and the detail says it is reading. A later open finds the index and answers in under two seconds.

The screen is the [groom dashboard](../gui/screens/groom-dashboard.md#history-filters). The rows come from [get-run-history](../http/get-run-history.md) with `archives=1`, the Overview from [get-archive-overview](../http/get-archive-overview.md), and a retry from [retry-history-summary](../http/retry-history-summary.md).

- code: groom/groom/archive.py::_summary_of@98085124a958
- code: groom/groom/archive.py::archive_run@e4717432f571
- code: groom/groom/archive.py::exact_dir@d1cf254049e7
- code: groom/groom/archive.py::is_indexed@a3e0a78e4854
- code: groom/groom/history.py::keep_archived@4d9427b9df86
- code: groom/groom/history.py::discover_archives@2f2469144910
- code: groom/groom/history.py::compute_archive@3229ef9e303b
- code: groom/groom/history.py::retry@109fc9780a80
- code: groom/groom/overview.py::stored_overview@085a2ec7726c
- code: groom/groom/app.py::_archive_overview@c3bd4430105d
- code: groom/groom/app.py::_summary_pass@88f8d7f4556e
- code: groom/groom/pools.py::ARCHIVE@9f14083a924c
- code: groom/groom/assets/dashboard.js::ArchiveGone@14177614ee11
- code: groom/groom/assets/dashboard.js::loadOverview@c2590f259fb2
- extends: [run history summary](run-history-summary.md)
- rule: the range filter offers Everything, archives included, beside the last 30 days and the last 7 days, and only that choice lists an archived run, so the default list and its totals read as they did before.
- rule: an archive's summary is computed in `archive_run` before its rows are dropped and stored in the manifest, and the stored summary table holds one row per archive with the flag `archived`, so the list needs no read of any archive that has one.
- rule: an archive with no summary is listed from its folder name and manifest as being read, and one background read on the archive pool fills it in once, so the row appears with its figures without a reload and the totals say how many summaries are still being read.
- rule: the frozen archive file is never rewritten, by the background read, by an open or by the sweep, and retention and the sweep stay as they were.
- rule: the Overview of an archive is read from the frozen file through `archive.run_source`, entered inside the pooled function, because the pool does not copy the context variable that redirects the reads.
- rule: the route resolves the run by its exact id and answers 404 when the stored summary is not an archived run's, because `run_source` falls back to the live store and the archive lookup falls back to a prefix match.
- rule: an archive has an Overview tab and no Files, Diff or Activity tab, because its checkout and its live records are gone.
- rule: the first open of an archive says it is reading and shows no problem count, and a later open shows no reading state, because the index beside the file already exists, and it answers in under two seconds.
- rule: archive reads run on a pool of their own, so the dashboard's queries never wait on them, and History answers while every archive read worker is busy.
- rule: an archive whose telemetry file is gone keeps its row, and its detail shows the stored summary's tiles and facts with the words files are gone, and no breakdown.
- rule: an unreadable summary keeps its row with no figures, says could not be read in place of the ending, and offers Retry now, which asks the background read again without opening the run.
- rule: an archive that cannot be opened says so in the detail and offers a retry, and the list stays.
- rule: a run archived under a derived folder name gets no second row, because the manifest names the run it describes.
- rule: the [median](run-median-comparison.md) is taken over the store and the archives together, so an archived run counts in the median and is compared with it.
- tests: groom/tests/test_archive_history.py::test_the_median_is_taken_over_the_store_and_the_archives_together
- tests: groom/tests/test_archive_history.py::test_the_manifest_of_a_new_archive_carries_the_summary_computed_before_its_rows_were_dropped
- tests: groom/tests/test_archive_history.py::test_an_archived_run_keeps_a_summary_row_flagged_archived_and_listed_only_with_archives
- tests: groom/tests/test_archive_history.py::test_an_older_archive_without_a_summary_gets_a_pending_row_from_its_manifest
- tests: groom/tests/test_archive_history.py::test_the_listing_counts_the_archives_no_row_stands_for_yet_and_discovery_clears_it
- tests: groom/tests/test_archive_history.py::test_one_background_read_fills_the_pending_row_without_rewriting_the_frozen_file
- tests: groom/tests/test_archive_history.py::test_an_archive_that_cannot_be_read_keeps_its_row_marked_unreadable_and_a_retry_asks_again
- tests: groom/tests/test_archive_history.py::test_a_retry_changes_nothing_for_a_run_that_is_not_an_unreadable_archive
- tests: groom/tests/test_archive_history.py::test_a_derived_archive_folder_name_does_not_get_a_second_row
- tests: groom/tests/test_archive_history.py::test_the_listing_reads_no_telemetry_file_per_row
- tests: groom/tests/test_archive_history.py::test_an_archived_runs_cost_and_times_per_node_and_flow_equal_the_terminal_reports
- tests: groom/tests/test_archive_history.py::test_the_archive_route_reads_an_archive_by_its_exact_id_inside_the_pool_thread
- tests: groom/tests/test_archive_history.py::test_the_archive_route_does_not_open_a_run_the_live_store_still_holds
- tests: groom/tests/test_archive_history.py::test_an_archive_whose_telemetry_file_is_gone_answers_from_the_stored_summary
- tests: groom/tests/test_archive_history.py::test_the_retry_route_puts_an_unreadable_summary_back_in_the_queue
- tests: groom/tests/test_archive_history.py::test_a_summary_pass_reads_the_older_archives_on_the_archive_pool
- tests: groom/tests/test_archive_history.py::test_archive_reads_have_a_pool_of_their_own_so_the_dashboard_queries_never_wait_on_them
- tests: groom/tests/test_archive_history.py::test_history_answers_while_every_archive_read_worker_is_busy
- tests: groom/tests/test_archive_history.py::test_a_sweep_leaves_an_existing_archive_file_untouched
- tests: groom/tests/test_archive_history.py::test_a_writer_failure_while_summarizing_still_archives_the_run_without_a_summary
- tests: groom/tests/test_history_archives_dynamic.py::test_the_first_open_of_an_archive_says_it_is_reading_then_shows_the_overview_with_no_files_diff_or_activity_tab
- tests: groom/tests/test_history_archives_dynamic.py::test_a_later_open_of_an_archive_shows_no_reading_state_and_the_overview_comes_in_under_two_seconds
- tests: groom/tests/test_history_archives_dynamic.py::test_an_archive_whose_files_are_gone_keeps_its_row_and_shows_the_stored_tiles_and_facts
- tests: groom/tests/test_history_archives_dynamic.py::test_an_archive_that_cannot_be_opened_says_so_in_the_detail_and_a_retry_shows_the_overview
- tests: groom/tests/test_history_archives_dynamic.py::test_an_unreadable_summary_shows_the_row_with_no_figures_says_so_and_retry_now_asks_again
- tests: groom/tests/test_history_archives_dynamic.py::test_pressing_enter_on_retry_now_asks_again_and_does_not_open_the_run
- tests: groom/tests/test_history_archives_dynamic.py::test_the_archive_surfaces_pass_an_axe_scan
