---
type: concept
slug: run-ending-banner
title: Run ending banner
---
# Run ending banner

An operator opens a run that stopped and needs to know why and how to go on. The banner at the top of that run's Overview answers both. It names the node where the run ended and the error class, says in a sentence what happened, links to the failing row in the Activity tab, and shows the command that continues the run with a control that copies it.

The banner is the `ending` member of the run's [Overview](../http/get-run-overview.md), composed on the server from the run's stored [history summary](run-history-summary.md) and its activity timeline. The ending itself comes from the [run ending mapping](run-ending-mapping.md). The same pane shows the work items tile, whose cost per item for an ended run reads `$X per item` and, for a run that ended in success, its difference from the median, as described by [overview tiles](overview-tiles.md) and the [run median comparison](run-median-comparison.md). The screen is the [groom dashboard](../gui/screens/groom-dashboard.md#detail-ending-banner).

- code: groom/groom/banner.py::banner@55f289d13d79
- code: groom/groom/history.py::summarize@b25e47db2c11
- code: groom/groom/history.py::_launch_record@a6c29de69bf3
- code: groom/groom/app.py::_overview_with_ending@80eed7ace691
- code: groom/groom/assets/dashboard.js::EndingBanner@e4949071c6e1
- code: groom/groom/assets/dashboard.js::openMoment@11ef31e84f7e
- rule: a run that ended failed, interrupted, crashed or gave up has a banner at the top of its Overview, and a successful run and a run with no recorded ending have none
- rule: the banner heading names the node where the run ended and the error class, as `Ended at <node>: <error>`, and names only the error class when the run recorded no node
- rule: an interrupted run's heading reads `Ended at <node>: interrupted by <what interrupted it>` and a crashed run's reads `Ended at <node>: crashed`, so the banner names what stopped the run in words and never by colour alone
- rule: the banner says in one sentence what happened, taken from the first line of the failing span's whole message, the same text the Activity reading pane shows, and never from the shorter text of the timeline row. A message over 240 characters ends at a word boundary with an ellipsis and no period. It is followed by how many work items finished, as `N of M work items finished.`, `No work item finished.` or `The work item finished.`
- rule: a crashed run has the fixed sentence `The run stopped on an unhandled error before it could finish.`, because a crash records no message of its own
- rule: a run that gave up says it finished with the work item skipped after exhausting its retries, and shows no command, because a gave-up run is complete and has nothing to continue
- rule: the command is one line, `cd <cwd> && <resume argv>`, built only from the launch record: the recorded `cwd` and the recorded resume argv, each shell-quoted so a path with a space survives a paste. A record with an empty `cwd` shows the argv alone. The `cd` is there because workhorse resumes from the recorded directory, so without it the command continues the run only from that one folder. The dashboard composes nothing from workflow names or flags.
- rule: the command shows for a failed, interrupted or crashed run only, with a copy control that copies it and says `Copied`
- rule: a container run's banner says to run the command inside the container it ran in, because the recorded program and paths exist there, and a native run's says to run it from a terminal, with the same `cd` form because the record's paths are container paths
- rule: a run whose folder is gone says it cannot be continued and shows no command, and a run whose folder stays but recorded no launch command says it recorded no launch command and shows no command, so the banner never offers a command that cannot work
- rule: the launch record is read once when the run's summary is written and stored with it, a container run's through the volume its workflow mounts, and an ended run summarized before the record was read is summarized again once. The stored command carries a read version, so a run summarized with an older form of the command is summarized again once.
- rule: the link opens the Activity tab with the run's last failed row selected and its turn or step in the reading pane, a failed turn by its turn and any other failed step by its span, and a run with no failing row has the banner with no link
- rule: the link and the copy control are buttons with accessible names and work from the keyboard, and the banner is a labelled region whose heading is a level two heading
- rule: History has no stop, resume or rewind control, because the banner only shows the command and the operator runs it outside the dashboard
- rule: the Overview route carries the banner as its `ending` member, composed on the server from the stored summary, so the browser composes no sentence and no command
- tests: groom/tests/test_history_banner.py::test_a_failed_runs_banner_names_the_node_where_it_ended_and_the_error_class
- tests: groom/tests/test_history_banner.py::test_the_banner_says_in_one_sentence_what_happened_and_how_many_work_items_finished
- tests: groom/tests/test_history_banner.py::test_a_long_failure_message_ends_the_banner_sentence_at_a_word_with_an_ellipsis_and_no_period
- tests: groom/tests/test_history_banner.py::test_a_failure_message_under_the_limit_reaches_the_banner_whole_past_the_activity_cut
- tests: groom/tests/test_history_banner.py::test_a_recorded_directory_with_a_space_survives_a_paste_into_a_shell
- tests: groom/tests/test_history_banner.py::test_a_launch_record_with_an_empty_cwd_shows_the_argv_alone
- tests: groom/tests/test_history_banner.py::test_a_summary_stored_before_the_cwd_was_read_is_summarized_again_once
- tests: groom/tests/test_history_banner.py::test_an_interrupted_or_crashed_run_has_the_same_banner_naming_what_stopped_it
- tests: groom/tests/test_history_banner.py::test_a_run_that_gave_up_has_a_banner_saying_it_skipped_the_work_item_and_shows_no_command
- tests: groom/tests/test_history_banner.py::test_a_successful_run_and_a_run_with_no_recorded_ending_have_no_banner
- tests: groom/tests/test_history_banner.py::test_the_link_names_the_failing_turns_row_in_the_activity_timeline
- tests: groom/tests/test_history_banner.py::test_a_run_with_no_failing_row_in_its_timeline_has_the_banner_with_no_link
- tests: groom/tests/test_history_banner.py::test_the_command_is_the_resume_argv_the_run_recorded_at_launch_flags_included
- tests: groom/tests/test_history_banner.py::test_a_container_runs_banner_carries_the_command_and_says_it_runs_inside_the_container
- tests: groom/tests/test_history_banner.py::test_a_run_whose_folder_is_gone_says_it_cannot_be_continued_and_shows_no_command
- tests: groom/tests/test_history_banner.py::test_a_run_whose_folder_stays_but_recorded_no_launch_says_so_and_composes_no_command
- tests: groom/tests/test_history_banner.py::test_the_overview_route_carries_the_ending_banner_of_a_stopped_run_and_none_for_a_finished_one
- tests: groom/tests/test_history_banner_dynamic.py::test_a_failed_runs_overview_starts_with_the_banner_and_a_successful_run_has_none
- tests: groom/tests/test_history_banner_dynamic.py::test_the_link_opens_the_activity_tab_with_the_failing_row_selected_and_its_step_in_the_reading_pane
- tests: groom/tests/test_history_banner_dynamic.py::test_the_banner_shows_the_recorded_command_and_the_copy_control_copies_it_and_says_copied
- tests: groom/tests/test_history_banner_dynamic.py::test_a_container_runs_banner_says_the_command_runs_inside_that_container
- tests: groom/tests/test_history_banner_dynamic.py::test_a_runs_banner_says_it_cannot_be_continued_when_its_folder_is_gone_and_shows_no_command
- tests: groom/tests/test_history_banner_dynamic.py::test_the_work_items_tile_of_an_ended_run_shows_the_cost_per_item_with_no_median_comparison
- tests: groom/tests/test_history_banner_dynamic.py::test_history_offers_no_stop_resume_or_rewind_control_on_a_stopped_run
- tests: groom/tests/test_history_banner_dynamic.py::test_the_banner_passes_an_axe_scan_and_its_link_and_copy_control_work_from_the_keyboard
