---
type: endpoint
slug: get-run-activity
title: get-run-activity
---
# get-run-activity

- server: [groom server](groom.md)
- method: `GET`
- path: `/api/run/{run_id}/activity`
- does:
  - Returns `rows`, one row per agent turn of the run, oldest first by `started_ts`, with the slug as the tie-break.
- verify: json_path(path="$.rows[0].slug", matches="^\\d{3}-\\d{5}-")
- does:
  - Builds a finished turn's row from the run's stored spans, with `node`, `visit`, `work_id`, `flow`, `pass`, `model`, `started_ts`, `ended_ts`, `duration_s`, `cost_usd`, `output_tokens`, `cache_read_tokens`, `status`, `result` and `session_id`.
- verify: json_path(path="$.rows[0].status", matches="^(done|failed|running)$")
- does:
  - Reports `status` `failed` when the turn's last span ended in error and `done` otherwise.
- does:
  - Lists a turn that has live transcript rows and no span yet as a running row, whose figures that need the turn's end are null.
- verify: json_path(path="$.rows[-1].status", equals="running")
- does:
  - Gives `result` as the first line of the turn's recorded `summary` or `notes`, else the first line of the span's activity label, else for a running turn the first line of its last agent message.
- does:
  - Gives `cost_usd` as the sum of the turn's priced spans, and null when none is priced, never `0`.
- does:
  - Numbers `pass` by the turn's position among the visits of its node within its flow, as the [run flow tree](../concepts/run-flow-tree.md) counts them.
- does:
  - Gives a turn of a run that predates the slug span attribute the slug of the one stored turn record that fits it, as [run Activity tab](../concepts/run-activity-tab.md) states. A turn with no single fit gets a stable `unmatched-<span id>` slug and `matched` false.
- verify: json_path(path="$.rows[0].matched", equals=true)
- does:
  - Returns `as_of`, the time the server built the list.
- does:
  - Reads the live transcript of a running turn from the run's capped live history, and does not mutate workflow state, the telemetry store or any websocket client.
- response:
  - media: `application/json`
  - body: `{"run_id": str, "rows": [{"slug": str, "node": str, "visit": str, "work_id": str, "flow": str, "pass": int, "model": str, "started_ts": float, "ended_ts": float | null, "duration_s": float | null, "cost_usd": float | null, "output_tokens": int, "cache_read_tokens": int, "status": str, "result": str, "session_id": str, "matched": bool}, ...], "as_of": float}`. An unknown run id returns an empty `rows`.
- status: `200`
- verify: http_status(code=200, path="/api/run/{run_id}/activity")
- code: groom/groom/app.py::run_activity@ee906a04819d
- code: groom/groom/activity.py::timeline@30f4cd17fc42
- detail: [groom activity module](../concepts/groom-activity-module.md)
- tests: groom/tests/test_activity.py::test_the_timeline_lists_a_finished_turn_with_its_figures_and_pass
- tests: groom/tests/test_activity.py::test_a_turn_with_no_span_yet_is_running_and_reads_from_the_live_rows
- tests: groom/tests/test_activity.py::test_a_turns_result_is_its_recorded_summary_before_the_spans_activity_label
- tests: groom/tests/test_activity.py::test_the_endpoints_answer_the_list_the_turn_and_the_two_failures

The route is `GET /api/run/{run_id}/activity`, registered by the [groom server](groom.md) and requested through the [serve-run-activity](groom.md#serve-run-activity) invocation. The path variable `run_id` is the telemetry run id from the run detail payload. The request has no query, no required headers and no body. The list holds figures and one line of result per turn and no transcript text, so it stays small however long the turns are. A failed read of the store is a framework-level `500`, which the dashboard shows as a failed Activity tab with a retry.
