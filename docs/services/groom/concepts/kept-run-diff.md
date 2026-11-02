---
type: concept
slug: kept-run-diff
title: Kept run diff
---
# Kept run diff

When a container run's sidecar stops answering, the [groom dashboard](../gui/screens/groom-dashboard.md) keeps the last diff it read in this page and marks it stale, so the operator can still read what the run had changed and is told in words that the sidecar is gone. The [Diff tab screen contract](../gui/screens/groom-dashboard.md#detail-diff-stale-strip) holds the strip and the marks. This page holds the decisions behind them, beside [run Diff tab](run-diff-tab.md) and [run Files tab](run-files-tab.md). The reply members involved are in [workspace diff data](../formats/workspace-diff-data.md).

- code: groom/groom/assets/dashboard.js::keepDiff@77539e304d52
- code: groom/groom/assets/dashboard.js::showKept@a4891ce5dcd6
- code: groom/groom/assets/dashboard.js::sidecarTrack@b8ea12a87722
- code: groom/groom/assets/dashboard.js::StaleStrip@39951b23e3bf
- code: groom/groom/assets/dashboard.js::loadRunDiff@6b1e2d0423d6
- code: groom/groom/app.py::diff@09402337f758
- rule: the browser holds the kept diff in page memory, per run, per checkout and per view, and the server stores nothing new. A reload loses it.
- rule: only a run selected in this page keeps a diff, and only a view the page read keeps one. A run first selected after its sidecar dropped shows no Files or Diff tab, because the page has nothing to keep.
- rule: the row's `sidecar` field tells the page the sidecar dropped. The mark shows while the run is a live container run, the row says no sidecar, and the page holds a kept diff for it.
- rule: the file, file content and diff replies carry `served`, `sidecar` or `volume`, as an addition beside the existing members. A volume reply never replaces a kept diff and never clears the mark, because it is a read of the same checkout at an unknown later time that the sidecar did not witness.
- rule: the mark is words, never colour alone. The Diff tab carries a `stale` chip and its accessible name says `Diff, stale`, and a strip above the diff says the sidecar stopped answering and how long ago, that the run may still be working, and the clock time the diff was read.
- rule: the strip's age ticks on the dashboard's shared second clock, which adds no second timer, and the strip is not a live region so the ticking is not announced.
- rule: the diff, the selected file and the scroll position stay as they were when the sidecar dropped. The stale view is not dimmed, because a dimmed foreground fails the contrast bar and CSS cannot close that.
- rule: while the mark shows, one `Retry now` control replaces the refresh control. It is a button in the strip, with a name and keyboard operation, and it reads through the same code as `Read the diff again`.
- rule: a retry that finds no sidecar leaves the diff and its read time alone and says the sidecar is still not answering. A failed read while the row still says no sidecar counts the same, so a failure never replaces a kept diff.
- rule: a retry never clears the kept files first, and a kept diff is replaced only by a read the sidecar answered.
- rule: when the sidecar reconnects, the page reads the diff again through the Refresh path, the mark and the strip clear, and the selected file stays if it is still in the diff.
- rule: the kept diff is per checkout and per view. A view the page had not read before the drop says it was not read before the sidecar stopped answering, and offers `Retry now`.
- rule: a run selected here whose sidecar drops before any diff was read says that no diff was read and offers `Retry now`.
- rule: selecting another run and coming back shows the same kept diff, checkout, read time and mark.
- rule: the Files tab keeps nothing. During the mark it says the sidecar stopped answering, that the run may still be working, and offers `Retry now`, and it reads the tree again when the sidecar returns.
- rule: when the run ends during the mark, the tabs go and the Overview tab shows. A reload during the mark shows no tabs.
- tests: groom/tests/test_diff_stale_dynamic.py::test_a_drop_keeps_the_diff_tab_marked_stale_in_words_with_a_strip_naming_the_read_time
- tests: groom/tests/test_diff_stale_dynamic.py::test_the_strip_counts_how_long_ago_on_the_shared_clock_without_a_live_region
- tests: groom/tests/test_diff_stale_dynamic.py::test_the_diff_selected_file_and_scroll_stay_as_they_were
- tests: groom/tests/test_diff_stale_dynamic.py::test_a_retry_replaces_the_refresh_control_while_the_mark_shows_and_works_from_the_keyboard
- tests: groom/tests/test_diff_stale_dynamic.py::test_a_retry_that_finds_no_sidecar_leaves_the_diff_and_its_time_alone_and_says_so
- tests: groom/tests/test_diff_stale_dynamic.py::test_a_reconnect_reads_again_clears_the_mark_and_keeps_the_selected_file
- tests: groom/tests/test_diff_stale_dynamic.py::test_the_kept_diff_is_per_checkout_and_per_view_and_a_view_not_read_says_so
- tests: groom/tests/test_diff_stale_dynamic.py::test_a_run_selected_here_whose_sidecar_drops_before_a_diff_was_read_says_none_was_read_and_offers_a_retry
- tests: groom/tests/test_diff_stale_dynamic.py::test_a_run_first_selected_after_the_drop_shows_no_files_or_diff_tab
- tests: groom/tests/test_diff_stale_dynamic.py::test_files_says_the_sidecar_stopped_answering_offers_a_retry_and_clears_on_reconnect
- tests: groom/tests/test_diff_stale_dynamic.py::test_selecting_another_run_and_coming_back_shows_the_same_kept_diff_and_mark
- tests: groom/tests/test_diff_stale_dynamic.py::test_the_tabs_go_and_overview_shows_when_the_run_ends_during_the_mark
- tests: groom/tests/test_diff_stale_dynamic.py::test_a_reload_during_the_drop_shows_no_tabs
- tests: groom/tests/test_diff_stale_dynamic.py::test_a_volume_reply_never_replaces_the_kept_diff
- tests: groom/tests/test_diff_stale_dynamic.py::test_the_strip_and_marks_pass_the_accessibility_scan
- tests: groom/tests/test_diff_stale_dynamic.py::test_the_kept_diff_after_a_real_drop_is_the_diff_git_reports_for_the_checkout
