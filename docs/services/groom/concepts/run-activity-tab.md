---
type: concept
slug: run-activity-tab
title: Run Activity tab
---
# Run Activity tab

The Activity tab answers one question about a run: what did each agent turn say and do. The Overview shows where the time and money went, and the Details tab shows the run's live metrics and telemetry trail. Neither shows the words of a turn. The Activity tab lists the run's agent turns, and the steps, gates, retries and churn alerts around them, under the work item and flow pass they happened in. The operator opens a turn to read its messages and one line per tool call, or any other row to read its name, time and one-line result, beside the list.

The tab sits between Overview and Details in the [detail tab bar](../gui/screens/groom-dashboard.md#detail-tabs) and is there for every run, native or container, with or without a sidecar. A turn's figures come from the run's stored spans through [get-run-activity](../http/get-run-activity.md), and a turn's words come from its stored record or, while it runs, from the run's live transcript, through [get-run-turn](../http/get-run-turn.md). The browser holds one list, the fold state of its headings and one open row.

Transcript text is untrusted. A model or a tool can write any characters, so no part of a turn reaches the page as markup the server or the browser did not choose.

- code: groom/groom/activity.py::timeline@7ae2217373d7
- code: groom/groom/activity.py::turn@a2d68ce89ba6
- code: groom/groom/app.py::run_activity@ee906a04819d
- code: groom/groom/app.py::run_turn@b044082c2db0
- code: groom/groom/assets/dashboard.js::ActivityTab@f909e1eeee52
- code: groom/groom/assets/dashboard.js::TranscriptText@53282490d240
- code: groom/groom/churn.py::alerts@641e36a47ca5
- code: groom/groom/flows.py::span_passes@55f223c1146d
- extends: [run flow tree](run-flow-tree.md)
- rule: the list groups its rows under a work item heading, then a flow pass heading, and one row is one visit. A node that runs twice has two rows. A run with no work item reads as one unnamed item whose heading is left out, so the flow pass headings stand directly in the list. Work done outside any work item is the first group, headed `Outside any work item`, and work outside any flow is a pass headed `outside any flow`.
- rule: one row is one visit, the turns of one slug under one parent span, so a retry inside a visit stays one row. A slug that a resumed pass repeats gives one row per visit, each under its own heading and each with its own start, time, cost and pass, so the rows of a pass add up to its heading. The first visit keeps the plain slug as its key. A later visit's key adds `~` and the millisecond its own turns began, which does not change when the list is read again. A row reads only the records of its own visit. When the archive kept none for it, the pane says its record could not be matched and offers no retry.
- rule: a pass number counts from one within one work item and one flow, in the order the pass headings are shown, so the headings of a work item read `dev · 1st pass`, `dev · 2nd pass`, `dev · 3rd pass` with no gap and none out of order. A run with no work item counts within the flow across the run. The pane head of a turn shows the number of the heading the turn sits under.
- rule: a work item heading carries its state, active time and cost from the same figures as the Overview's work item table, so the two agree. A flow pass heading carries its state, time and cost from the flow tree's leaf rule, so the passes of one flow add up to that flow's row in the Overview.
- rule: a work item's state reads `running` while its turn runs, `in progress` for the newest item of a live run, then `done`, `not counted` or `count unknown` from the Overview's outcome. A flow pass reads `running`, `open`, `failed` or `passed`.
- rule: a heading is a button that opens and closes its rows, with `aria-expanded` and an accessible name that says its state, time and cost in words. A finished work item or flow pass starts folded. The item and the pass in progress start open. The group holding the selected row is open whatever the fold state. A choice the operator made on a heading holds across reads.
- rule: a run of successful steps folds to one row that says the count, the time and `all passed`. Selecting the row opens it into one row per step, and selecting it again closes it. A failed step, a gate, a backend retry and a churn alert each stand as their own row between the folds, and each has a mark of its own, a cross, a question mark or an exclamation mark, so the kind never rests on color alone.
- rule: selecting a step, a failed step, a gate, a retry or a churn alert shows its name, its time and its one-line result in the pane in place of a transcript. A failed step's result is its error message, and a gate's is its question or activity label with how it ended.
- rule: a retry comes from the `retry` event on the turn's span and a churn alert from replaying the churn rule over the run's stored spans, so both come back unchanged after groom restarts and nothing is stored apart from the spans.
- rule: a turn that is running has its own mark and is the last row of its flow pass. Its figures come from the live rows until it ends, and it is placed in the group last worked in.
- rule: a heading stays in view while its rows scroll, the flow pass heading under the work item heading it sits in.
- rule: the tab opens on the newest turn, the last row of the list, and selecting another row opens that one. A list that is read again keeps the open turn when its row is still there, and otherwise opens the newest.
- rule: a turn of a run recorded before spans carried a visit slug takes the slug of the one stored turn record of the same node and session whose time lies within 5 seconds of the span's start and end. When exactly one record fits, the turn reads from that record. When none fits or several fit, the turn gets the stable key `unmatched-<span id>`, its pane says its record could not be matched, and the server never retries the match or guesses between records.
- rule: a message renders as Markdown. Raw HTML inside it shows as literal text, an image shows as its alt text and produces no image element, and the result goes through DOMPurify before it is set as markup. A client where the Markdown renderer or the sanitizer did not load shows the message as plain text with its line breaks kept.
- rule: a turn's result is the first line of its recorded `summary`, else of its recorded `notes`, else of the span's activity label, else for a running turn the first line of its last agent message. The row and the pane head show that line and never a line the operator has to open the turn to find.
- rule: a finished turn reads only the entries inside its own window, from 5 seconds before its start to 5 seconds after its end. A session resumed across turns holds earlier turns' lines in the same file, and the window is what keeps them out of this turn.
- rule: a running turn shows only the figures it has. Its head omits the model, the cost, the pass and the output tokens, because none is known before the turn ends. The cost reads `lands at turn end`.
- rule: the live history holds the last 200 updates, so a long running turn can lose its start. A turn read from it whose first update is gone says `Earlier output of this turn is not shown`.
- rule: a turn outside any flow node shows no pass. The head never reads `pass 0` or `0th pass`.
- rule: the tab reads the list once when it opens and again when the run's figures revision moves, and while a turn runs it reads the list and the open turn every 3 seconds. Both reads keep the operator's scroll and selection.
- rule: a list that fails to read says so with a retry and never reads as empty. A turn that fails to read says so with a retry and keeps the list. A run with no turn says it has no activity yet and whether the run is alive.
- rule: the tab shows the agent's messages and tool calls only. The prompt, the model's thinking and archived runs' turns stay out of it.
- tests: groom/tests/test_activity_tab_dynamic.py::test_the_activity_tab_sits_between_overview_and_details
- tests: groom/tests/test_activity_tab_dynamic.py::test_the_tab_lists_turns_oldest_first_each_with_time_node_duration_cost_and_result
- tests: groom/tests/test_activity_tab_dynamic.py::test_html_in_a_message_or_a_tool_line_renders_as_text_and_no_script_runs
- tests: groom/tests/test_activity_tab_dynamic.py::test_a_message_written_in_markdown_reads_as_formatted_prose
- tests: groom/tests/test_activity_tab_dynamic.py::test_a_turn_of_an_old_run_matches_its_one_archived_record_and_a_turn_with_none_says_so
- tests: groom/tests/test_activity_tab_dynamic.py::test_a_running_turn_whose_start_the_live_history_dropped_says_earlier_output_is_not_shown
- tests: groom/tests/test_activity.py::test_an_old_span_with_several_matching_rows_picks_none_of_them
- tests: groom/tests/test_activity_groups.py::test_rows_group_under_a_work_item_with_its_state_time_and_cost
- tests: groom/tests/test_activity_groups.py::test_inside_a_work_item_rows_group_under_a_flow_pass_with_its_state_time_and_cost
- tests: groom/tests/test_activity_groups.py::test_a_node_that_runs_twice_has_two_rows
- tests: groom/tests/test_activity_groups.py::test_a_run_of_successful_steps_folds_to_one_entry_with_the_count_and_the_time
- tests: groom/tests/test_activity_groups.py::test_a_failed_step_stands_as_its_own_entry_between_the_folds
- tests: groom/tests/test_activity_groups.py::test_a_gate_a_retry_and_a_failed_step_each_have_their_own_entry_with_name_time_and_result
- tests: groom/tests/test_activity_groups.py::test_a_churn_alert_has_its_own_entry_derived_from_the_stored_spans
- tests: groom/tests/test_activity_groups.py::test_retries_and_churn_alerts_come_back_from_the_stored_spans_after_a_restart
- tests: groom/tests/test_activity_groups.py::test_the_running_turn_is_the_last_entry_of_its_pass_marked_running
- tests: groom/tests/test_activity_groups.py::test_a_run_with_no_work_items_has_one_unnamed_item_holding_its_flow_passes
- tests: groom/tests/test_activity_groups.py::test_a_heading_adds_up_to_the_overviews_figures_for_that_work_item_and_flow
- tests: groom/tests/test_activity_groups.py::test_two_work_items_each_count_their_passes_from_first
- tests: groom/tests/test_activity_groups.py::test_passes_never_skip_or_reorder_in_display_order_even_when_a_visit_slug_repeats_across_passes
- tests: groom/tests/test_activity_groups.py::test_a_run_with_no_work_items_counts_each_flow_across_the_run
- tests: groom/tests/test_activity_groups.py::test_the_turn_readers_head_shows_the_number_of_the_heading_the_turn_sits_under
- tests: groom/tests/test_activity_groups.py::test_a_slug_a_resumed_pass_repeats_gives_two_rows_each_under_its_own_heading
- tests: groom/tests/test_activity_groups.py::test_a_retry_inside_one_visit_stays_one_row_with_its_attempts_summed
- tests: groom/tests/test_activity_groups.py::test_each_of_two_rows_sharing_a_slug_reads_only_its_own_records
- tests: groom/tests/test_activity_groups.py::test_a_visit_whose_record_the_archive_did_not_keep_is_not_matched_and_shows_no_other_visits_content
- tests: groom/tests/test_activity_groups.py::test_the_rows_under_a_pass_add_up_to_its_heading_on_a_repeated_slug_fixture
- tests: groom/tests/test_activity_groups.py::test_a_row_key_stays_the_same_across_two_reads
- tests: groom/tests/test_activity_groups_dynamic.py::test_each_work_item_gets_a_heading_with_state_time_and_cost_and_only_the_one_in_progress_starts_open
- tests: groom/tests/test_activity_groups_dynamic.py::test_inside_a_work_item_each_flow_pass_gets_a_heading_with_state_time_and_cost
- tests: groom/tests/test_activity_groups_dynamic.py::test_a_finished_flow_pass_starts_folded_and_the_pass_holding_the_open_turn_starts_open
- tests: groom/tests/test_activity_groups_dynamic.py::test_selecting_a_heading_opens_or_closes_it_by_pointer_and_by_keyboard
- tests: groom/tests/test_activity_groups_dynamic.py::test_a_node_that_runs_twice_has_two_rows_one_per_visit
- tests: groom/tests/test_activity_groups_dynamic.py::test_a_run_of_passed_steps_folds_to_one_line_and_selecting_it_opens_and_closes_one_row_per_step
- tests: groom/tests/test_activity_groups_dynamic.py::test_a_failed_step_stands_as_its_own_row_between_two_folds
- tests: groom/tests/test_activity_groups_dynamic.py::test_a_failed_step_a_gate_a_retry_and_a_churn_alert_each_get_a_row_with_a_different_mark
- tests: groom/tests/test_activity_groups_dynamic.py::test_selecting_a_problem_row_shows_its_name_its_time_and_its_one_line_result_in_the_pane
- tests: groom/tests/test_activity_groups_dynamic.py::test_selecting_a_turn_inside_a_group_reads_as_it_did
- tests: groom/tests/test_activity_groups_dynamic.py::test_the_running_turn_has_its_own_mark_as_the_last_row_of_its_flow_pass
- tests: groom/tests/test_activity_groups_dynamic.py::test_a_heading_stays_in_view_while_its_rows_scroll
- tests: groom/tests/test_activity_groups_dynamic.py::test_a_run_with_no_work_items_groups_its_rows_directly_under_the_flow_pass
- tests: groom/tests/test_activity_groups_dynamic.py::test_a_heading_adds_up_to_the_overview_figures_for_its_work_item
- tests: groom/tests/test_activity_groups_dynamic.py::test_headings_and_rows_keep_a_role_a_name_and_state_in_words_and_pass_an_axe_scan
- refs: [operator reads an agent turn](../flows/operator-reads-an-agent-turn.md), [groom activity module](groom-activity-module.md), [groom transcript parse module](groom-transcript-parse-module.md), [the groom dashboard detail pane](../gui/screens/groom-dashboard.md#detail-pane)
