---
type: endpoint
slug: get-run-turn
title: get-run-turn
---
# get-run-turn

- server: [groom server](groom.md)
- method: `GET`
- path: `/api/run/{run_id}/activity/{slug}`
- does:
  - Returns `head`, the same row the [list endpoint](get-run-activity.md) gives for the turn.
- verify: json_path(path="$.head.slug", equals="001-00001-code")
- does:
  - Returns `entries`, the turn's messages and tool calls in the order they happened, each either `{"kind": "message", "role", "text"}` or `{"kind": "tool", "name", "summary", "failed"}`.
- verify: json_path(path="$.entries[0].kind", matches="^(message|tool)$")
- does:
  - Keeps only messages with text under the `assistant` or `plan` role, never the prompt, the thinking or an empty message.
- verify: json_path(path="$.entries[*].role", matches="^(assistant|plan)$")
- does:
  - Reads a finished turn from its stored record and keeps only the entries inside the turn's own window, its start minus 5 seconds to its end plus 5 seconds, so a resumed session shows only this turn.
- verify: json_path(path="$.entries", matches="^\\[")
- does:
  - Reads a running turn from the run's live transcript rows, and reads a finished turn with no stored record from the live rows when the history still holds them.
- does:
  - Returns `cut` true when the live history dropped the start of the turn it read from, because the history keeps the last 200 updates. Otherwise `cut` is false.
- verify: json_path(path="$.cut", equals=false)
- does:
  - Returns an empty `entries` with status `200` for a turn whose slug starts `unmatched-`, because no record was matched to it, and never retries the match.
  - Reads a key of the form `<slug>~<milliseconds>` as a later visit of a slug that a resumed pass repeated. It returns that visit's records only, and an empty `entries` with status `200` when the archive kept none for it.
- does:
  - Sends transcript text as it was recorded and applies no markup of its own.
- response:
  - media: `application/json`
  - body: `{"run_id": str, "head": {...}, "entries": [{...}, ...], "cut": bool}`
- status: `200`
- verify: http_status(code=200, path="/api/run/{run_id}/activity/{slug}")
- errors:
  - `404` with detail `no such turn` when the run has neither a stored turn nor live rows under the slug.
- verify: json_path(path="$.detail", equals="no such turn")
- errors:
  - `503` with detail `the turn could not be read` when the turn exists but its record is not on this machine, which is a turn of a container run whose records the sidecar has not pulled yet, and the live history does not hold it.
- verify: json_path(path="$.detail", equals="the turn could not be read")
- code: groom/groom/app.py::run_turn@b044082c2db0
- code: groom/groom/activity.py::turn@a2d68ce89ba6
- detail: [groom activity module](../concepts/groom-activity-module.md)
- detail: [groom transcript parse module](../concepts/groom-transcript-parse-module.md)
- tests: groom/tests/test_activity.py::test_a_finished_turn_reads_only_its_own_window_and_drops_the_rest
- tests: groom/tests/test_activity.py::test_an_unknown_turn_is_not_found_and_an_unarchived_one_is_unreadable
- tests: groom/tests/test_activity.py::test_an_unmatched_turn_answers_200_with_no_entries_never_a_failure
- tests: groom/tests/test_activity.py::test_a_live_turn_whose_start_the_history_dropped_is_marked_cut
- tests: groom/tests/test_activity.py::test_the_endpoints_answer_the_list_the_turn_and_the_two_failures

The route is `GET /api/run/{run_id}/activity/{slug}`, registered by the [groom server](groom.md) and requested through the [serve-run-turn](groom.md#serve-run-turn) invocation. The `slug` is the `slug` of a row of [get-run-activity](get-run-activity.md), in the form `{generation}-{sequence}-{node}`. The request has no query, no required headers and no body. The dashboard reads one turn at a time, when the operator selects its row.
