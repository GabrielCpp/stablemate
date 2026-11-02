---
type: flow
slug: operator-reads-an-agent-turn
title: Operator reads an agent turn
---
# Operator reads an agent turn

This journey covers the as-built operator path through the Activity tab of a run in the [groom dashboard](../gui/screens/groom-dashboard.md): opening the [Activity tab](../gui/screens/groom-dashboard.md#detail-activity-tab) of a run, reading the list of its agent turns through [GET /api/run/{run_id}/activity](../http/get-run-activity.md), choosing a turn, and reading what the agent said and did through [GET /api/run/{run_id}/activity/{slug}](../http/get-run-turn.md). The tab works the same for a native run and a container run, and for a turn that has ended and one that is still running. The operator's acts are [open the Activity tab](../gui/screens/groom-dashboard.md#open-detail-activity-tab), [select a turn](../gui/screens/groom-dashboard.md#select-detail-activity-turn) and [retry a read that failed](../gui/screens/groom-dashboard.md#retry-detail-activity). The rules behind it are in [run Activity tab](../concepts/run-activity-tab.md).

Every response on this path is JSON. The server sends the turn's text as it was recorded, and the browser turns it into Markdown prose with raw HTML and images neutralised, so a model or a tool cannot put markup on the page.

- start: the groom server is running
- verify: http_status(code=200, title="Groom Dashboard", path="/")
- start: the browser has loaded the [groom dashboard](../gui/screens/groom-dashboard.md) with a run selected
- verify: http_status(code=200, path="/api/run/run-1/activity")
- steps:
  1. [Serve the run's turns](../http/groom.md#serve-run-activity)
  2. [Serve the turn](../http/groom.md#serve-run-turn)
  3. [Serve the step or gate](../http/groom.md#serve-run-entry)
- end: the Activity tab lists the run's turns oldest first under their work item and flow pass headings with exactly one row marked `aria-current`
- verify: json_path(path="$.rows[-1].slug", matches="^\\d{3}-\\d{5}-")
- end: the pane beside the list shows the selected turn's head, its messages as prose and each tool call as one line
- verify: json_path(path="$.entries[0].kind", matches="^(message|tool)$")
- end: a selected step or gate reads in the pane with its error or question, its logs or answer, and what came next
- verify: json_path(path="$.kind", matches="^(step|gate)$")
- detail: [run Activity tab](../concepts/run-activity-tab.md)
- detail: [groom activity module](../concepts/groom-activity-module.md)
- detail: [groom transcript parse module](../concepts/groom-transcript-parse-module.md)
- tests: groom/tests/test_activity_tab_dynamic.py::test_the_tab_lists_turns_oldest_first_each_with_time_node_duration_cost_and_result
- tests: groom/tests/test_activity_tab_dynamic.py::test_selecting_a_row_opens_the_turn_beside_the_list_and_marks_it_selected
- tests: groom/tests/test_activity_tab_dynamic.py::test_the_pane_shows_messages_as_prose_and_each_tool_call_as_one_line
- tests: groom/tests/test_activity_tab_dynamic.py::test_a_turn_that_cannot_be_read_says_so_keeps_the_list_and_a_retry_clears_it
