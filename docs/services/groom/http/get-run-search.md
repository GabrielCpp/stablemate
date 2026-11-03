---
type: endpoint
slug: get-run-search
title: get-run-search
---
# get-run-search

- server: [groom server](groom.md)
- method: `GET`
- path: `/api/run/{run_id}/search`
- does: all
  - Reads the transcript of every turn of the one run named in the path and returns the turns whose transcript says the query `q`, each with the first matching line.
  - Matches case-insensitively as a plain substring after collapsing runs of whitespace in the query.
  - Searches the messages, the tool summaries and the whole output of failed tool calls, never the prompt or the thinking.
  - Cuts the query to 200 characters.
  - Cuts each returned line to 160 characters around the match.
  - Reads no turn of another run.
  - Returns no matches and reads nothing for an empty query.
- verify: json_path(path="$.matches", matches="^\\[")
- response:
  - media: `application/json`
  - body: `{"run_id": str, "query": str, "matches": [{"key": str, "line": str}, ...]}`
- status: `200`
- verify: http_status(code=200, path="/api/run/{run_id}/search")
- errors:
  - `503` with detail `the transcripts could not be searched` when any turn of the run exists but its record is not on this machine yet. The dashboard keeps the row matches and offers a retry.
- verify: json_path(path="$.detail", equals="the transcripts could not be searched")
- code: groom/groom/app.py::run_search@60270d508d18
- code: groom/groom/activity.py::search@addb2fe1fa01
- detail: [groom activity module](../concepts/groom-activity-module.md)
- detail: [Run Activity tab](../concepts/run-activity-tab.md)
- tests: groom/tests/test_activity.py::test_a_search_finds_the_turn_whose_transcript_says_the_query_with_its_line
- tests: groom/tests/test_activity.py::test_a_search_never_reads_a_turn_outside_its_run_and_an_empty_query_reads_nothing
- tests: groom/tests/test_activity.py::test_a_search_line_is_cut_and_keeps_markup_as_plain_text
- tests: groom/tests/test_activity.py::test_an_unreadable_transcript_fails_the_search_and_the_endpoint_answers_503

The route is `GET /api/run/{run_id}/search?q=<text>`, registered by the [groom server](groom.md) and requested through the [serve-run-search](groom.md#serve-run-search) invocation. A `key` in `matches` is the `slug` of a row of [get-run-activity](get-run-activity.md).
