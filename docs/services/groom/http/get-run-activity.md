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
  - Returns `items`, the same turns grouped by work item then flow pass, each pass holding `entries` in time order. An entry is a `turn` or `running` row, a fold `steps` of passed steps, a `failed` step, a `gate`, a `retry`, a `churn` alert or, when asked, a `log` line.
- verify: json_path(path="$.items[0].passes[0].entries[0].kind", matches="^(turn|running|steps|failed|gate|retry|churn|log)$")
- does:
  - Gives each item its `work_id`, `outcome`, `latest`, `running`, `time_s` and `cost_usd` from the Overview's work item figures.
- does:
  - Returns a state span that holds no child span except infra spans as a step entry named by its node without the `state:` prefix, under the pass of its flow. Its seconds are added to the pass `time_s`, not to the item `time_s`, with no cost.
- does:
  - Gives each pass its `flow`, `pass`, `state`, `time_s` and `cost_usd` from the flow tree's leaf rule.
- does:
  - Derives a `retry` entry for each agent turn that follows an earlier attempt under the same parent, with the wait from the `retry` event the earlier attempt recorded, and `churn` entries from the churn rule replayed over the stored spans, so a restart loses neither.
  - Gives the `failed` entry of an agent turn a `turn` key naming its turn row.
  - Marks each `failed`, `retry` and `churn` entry `problem` true and returns `problems`, the count of those entries, which the Overview's problem count equals.
- does: all
  - Takes the optional query `logs`, which is `1` to place log lines.
  - With `logs=1` puts each log line of INFO level and above in the pass whose first turn started latest at or before the line, as an entry of kind `log` ordered by time among that pass's entries.
  - Without `logs` places no `log` entry and still returns `log_count`, the count of those lines.
  - Never lets a `log` entry split a fold of passed steps.
- verify: json_path(path="$.log_count", matches="^[0-9]+$")
- does:
  - Returns `as_of`, the time the server built the list.
- does:
  - Reads the live transcript of a running turn from the run's capped live history, and does not mutate workflow state, the telemetry store or any websocket client.
- response:
  - media: `application/json`
  - body: `{"run_id": str, "rows": [{"slug": str, "node": str, "visit": str, "work_id": str, "flow": str, "pass": int, "model": str, "started_ts": float, "ended_ts": float | null, "duration_s": float | null, "cost_usd": float | null, "output_tokens": int, "cache_read_tokens": int, "status": str, "result": str, "session_id": str, "matched": bool}, ...], "items": [{"work_id": str, "outcome": str, "latest": bool, "running": bool, "time_s": float, "cost_usd": float | null, "passes": [{"flow": str, "pass": int, "state": str, "time_s": float, "cost_usd": float | null, "first_ts": float, "entries": [{"kind": str, "key": str, "ts": float, ...}, ...]}, ...]}, ...], "problems": int, "log_count": int, "as_of": float}`. An unknown run id returns an empty `rows`.
- status: `200`
- verify: http_status(code=200, path="/api/run/{run_id}/activity")
- code: groom/groom/app.py::run_activity@a7f0fcdaf20d
- code: groom/groom/activity.py::timeline@29dffacc393b
- detail: [groom activity module](../concepts/groom-activity-module.md)
- tests: groom/tests/test_activity_problems.py::test_every_count_of_problems_reads_one_definition
- tests: groom/tests/test_activity.py::test_the_timeline_lists_a_finished_turn_with_its_figures_and_pass
- tests: groom/tests/test_activity.py::test_a_turn_with_no_span_yet_is_running_and_reads_from_the_live_rows
- tests: groom/tests/test_activity.py::test_a_turns_result_is_its_recorded_summary_before_the_spans_activity_label
- tests: groom/tests/test_activity.py::test_the_endpoints_answer_the_list_the_turn_and_the_missing_turn
- tests: groom/tests/test_activity_groups.py::test_rows_group_under_a_work_item_with_its_state_time_and_cost
- tests: groom/tests/test_activity_groups.py::test_a_gate_a_retry_and_a_failed_step_each_have_their_own_entry_with_name_time_and_result

The route is `GET /api/run/{run_id}/activity`, registered by the [groom server](groom.md) and requested through the [serve-run-activity](groom.md#serve-run-activity) invocation. The path variable `run_id` is the telemetry run id from the run detail payload. The request has the optional query `logs` and no required headers and no body. The list holds figures and one line of result per turn and no transcript text, so it stays small however long the turns are. A failed read of the store is a framework-level `500`, which the dashboard shows as a failed Activity tab with a retry.
