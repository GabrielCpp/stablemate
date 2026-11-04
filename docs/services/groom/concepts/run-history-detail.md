---
type: concept
slug: run-history-detail
title: Run history detail
---
# Run history detail

Selecting a row in History opens the run beside a narrowed column of the same runs. The detail is the one component the Runs pane renders, given an ended run, so the Overview and the Activity tab read the same way for a run that ended as for a run that is live, minus what only a live run has.

The detail is built in the browser from the run's [history row](run-history-summary.md) and from the run's own [Overview](../http/get-run-overview.md) and [activity](run-activity-tab.md) reads. The screen is the [groom dashboard](../gui/screens/groom-dashboard.md#open-history-run).

- code: groom/groom/assets/dashboard.js::endedDetail@d25fd1f1412b
- code: groom/groom/assets/dashboard.js::Detail@e1d4b94aa72a
- code: groom/groom/assets/dashboard.js::HistoryNarrow@51b05351f8ec
- code: groom/groom/assets/dashboard.js::HistoryDetail@3415c7123ea0
- code: groom/groom/assets/dashboard.js::openHistoryRun@1e7244010b4a
- code: groom/groom/assets/dashboard.js::closeHistoryRun@2dcc04fba758
- rule: selecting a row of the history table opens that run beside a column of the same runs, and the one run detail component renders it in History as in Runs, with no second detail
- rule: an ended run has the Overview and Activity tabs and never a Files or Diff tab, whether it ran natively or in a container, because its checkout is gone or no longer the run's
- rule: the head of an ended run says `ended`, its end time and its ending in words, and never shows a running chip, a burn rate or a current turn strip
- rule: the Overview of an ended run takes its figures from the same terminal queries as the Overview of a live run, so a run's cost and its times per node and per flow equal `groom cost` and `groom profile`, and the dashboard calculates none of them a second time
- rule: the Overview of a run that failed, was interrupted, crashed or gave up starts with the [run ending banner](run-ending-banner.md), and History offers no stop, resume or rewind control
- rule: a cost-less backend shows the labelled estimate in the cost tile and an output tokens column in place of cost in the breakdown, and an ended run's cost tile says how many turns were priced
- rule: a run recorded before the flow attributes existed still shows its flow times
- rule: the Activity tab of an ended run opens with finished items folded and has no follow control and no live pill, and an answered gate reads in Activity only, because the detail of an ended run has no answer box
- rule: the Activity badge, the attention tile and the problem column of the list show one number
- rule: while the run is read the detail says `Reading this run…` and clears when the Overview appears, and a failed read says the run's figures could not be read, offers a retry and keeps the list
- rule: selecting or closing a run keeps the [history filters](run-history-filters.md), and the narrowed column holds the runs that match them
- rule: closing the run returns the full table and puts focus on the run's row, and `j` and `k` open the next and previous run in History and move the timeline while Activity shows
- rule: the detail of an ended run is built in the browser from the history row and the run's own Overview and Activity reads, and groom adds no endpoint for it
- rule: a workflow chip in a narrowed row keeps one line at its natural width, and the repo and run text take the ellipsis
- rule: a narrowed row cuts a long run id or repo label off with an ellipsis and never pushes a column or a control out of view, and the head wraps the whole run id
- tests: groom/tests/test_history_open_dynamic.py::test_selecting_a_row_narrows_the_list_opens_the_detail_beside_it_and_marks_the_row_selected
- tests: groom/tests/test_history_open_dynamic.py::test_a_narrowed_row_shows_cost_with_priced_count_active_time_end_time_and_ending
- tests: groom/tests/test_history_open_dynamic.py::test_the_close_control_returns_to_the_full_table_and_the_detail_closes
- tests: groom/tests/test_history_open_dynamic.py::test_an_ended_run_has_overview_and_activity_tabs_and_no_files_or_diff_tab_even_when_it_ran_in_a_container
- tests: groom/tests/test_history_open_dynamic.py::test_the_run_head_says_ended_with_its_end_time_and_its_ending_in_words_and_no_running_chip
- tests: groom/tests/test_history_open_dynamic.py::test_the_overview_shows_the_same_sections_as_a_live_run_with_no_burn_rate_and_no_current_turn_strip
- tests: groom/tests/test_history_open_dynamic.py::test_the_sessions_table_says_how_each_session_stopped
- tests: groom/tests/test_history_open_dynamic.py::test_the_activity_tab_opens_the_timeline_with_finished_items_folded_no_follow_state_and_no_live_pill
- tests: groom/tests/test_history_open_dynamic.py::test_an_answered_gate_reads_in_activity_only_and_the_detail_has_no_answer_box
- tests: groom/tests/test_history_open_dynamic.py::test_the_activity_badge_the_attention_tile_and_the_list_problem_column_show_one_number
- tests: groom/tests/test_history_open_dynamic.py::test_a_backend_with_no_cost_shows_the_labelled_estimate_in_the_cost_tile_and_an_output_tokens_column_in_the_breakdown
- tests: groom/tests/test_history_open_dynamic.py::test_while_a_run_is_read_the_detail_shows_a_reading_state_that_clears_when_the_overview_appears
- tests: groom/tests/test_history_open_dynamic.py::test_a_failed_read_says_the_run_figures_could_not_be_read_keeps_the_list_and_a_retry_shows_the_overview
- tests: groom/tests/test_history_open_dynamic.py::test_j_and_k_open_the_next_and_previous_run_in_history_and_move_the_timeline_while_activity_shows
- tests: groom/tests/test_history_open_dynamic.py::test_every_new_control_has_a_role_an_accessible_name_and_keyboard_operation
- tests: groom/tests/test_history_open_dynamic.py::test_the_opened_history_has_no_accessibility_violations
- tests: groom/tests/test_history_open_dynamic.py::test_a_long_run_id_and_repo_label_stay_inside_the_narrowed_list_and_the_head_wraps_the_whole_id
- tests: groom/tests/test_history_open_dynamic.py::test_runs_and_history_render_the_one_detail_component
- tests: groom/tests/test_history.py::test_one_ended_runs_cost_and_times_per_node_and_per_flow_equal_groom_cost_and_groom_profile
- tests: groom/tests/test_history.py::test_a_run_recorded_before_the_flow_attributes_still_shows_its_flow_times
- tests: groom/tests/test_history.py::test_the_summary_the_overview_and_the_activity_count_report_one_problem_number
- tests: groom/tests/test_history_open_dynamic.py::test_a_workflow_chip_stays_on_one_line_at_its_natural_width_in_the_narrowed_list
- tests: groom/tests/test_history_open_dynamic.py::test_the_overview_uses_the_mock_wording_for_the_heading_the_clock_and_the_breakdown
- tests: groom/tests/test_history_open_dynamic.py::test_facts_and_sessions_write_a_time_without_a_comma_and_the_copy_button_keeps_a_gap
