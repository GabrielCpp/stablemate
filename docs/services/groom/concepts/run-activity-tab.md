---
type: concept
slug: run-activity-tab
title: Run Activity tab
---
# Run Activity tab

The Activity tab answers one question about a run: what did each agent turn say and do. The Overview shows where the time and money went, and the Details tab shows the run's live metrics and telemetry trail. Neither shows the words of a turn. The Activity tab lists the run's agent turns oldest first, and the operator opens one to read its messages and one line per tool call, beside the list.

The tab sits between Overview and Details in the [detail tab bar](../gui/screens/groom-dashboard.md#detail-tabs) and is there for every run, native or container, with or without a sidecar. A turn's figures come from the run's stored spans through [get-run-activity](../http/get-run-activity.md), and a turn's words come from its stored record or, while it runs, from the run's live transcript, through [get-run-turn](../http/get-run-turn.md). The browser holds one list and one open turn.

Transcript text is untrusted. A model or a tool can write any characters, so no part of a turn reaches the page as markup the server or the browser did not choose.

- code: groom/groom/activity.py::timeline@30f4cd17fc42
- code: groom/groom/activity.py::turn@01b84cdb4aec
- code: groom/groom/app.py::run_activity@ee906a04819d
- code: groom/groom/app.py::run_turn@b044082c2db0
- code: groom/groom/assets/dashboard.js::ActivityTab@46f65e17d3bd
- code: groom/groom/assets/dashboard.js::TranscriptText@53282490d240
- extends: [run flow tree](run-flow-tree.md)
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
- refs: [operator reads an agent turn](../flows/operator-reads-an-agent-turn.md), [groom activity module](groom-activity-module.md), [groom transcript parse module](groom-transcript-parse-module.md), [the groom dashboard detail pane](../gui/screens/groom-dashboard.md#detail-pane)
