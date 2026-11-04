---
type: endpoint
slug: get-run-records
title: get-run-records
---
# get-run-records

- server: [groom server](groom.md)
- method: `GET`
- path: `/api/run/{run_id}/records`
- does: all
  - Returns one page of the run's stored records, newest first, for the [Raw view](../concepts/run-activity-tab.md) of the Activity tab.
  - Lists a span as one record written when it ends, with its duration and, when priced, its cost, a log line at its own severity, a span event, a churn alert and, only when `metrics` is `1`, a metric sample.
  - Orders every record by one total order of time, then kind, then id, so two records with the same time keep one place across pages.
  - Takes `before`, the cursor a previous page returned, and returns only records older than it. An absent or empty `before` starts at the newest record.
  - Takes `limit`, at most 200, and returns the page size asked for within that cap.
  - Returns `total`, the count of every record the run has, with metric samples counted only when asked, and `metric_samples`, the count of the run's metric samples either way.
- verify: json_path(path="$.total", matches="^[0-9]+$")
- does: all
  - Returns `next`, the cursor of the page's last record, and an empty `next` on the last page, so a page that is full with nothing older has none.
- verify: json_path(path="$.next", equals="")
- does:
  - Reads the store on the query pool and does not write the telemetry store, mutate workflow state or broadcast a websocket frame.
- response:
  - media: `application/json`
  - body: `{"run_id": str, "records": [{"key": str, "id": int, "ts": float, "time": str, "kind": str, "node": str, "text": str, "tone": str}, ...], "total": int, "metric_samples": int, "metrics": bool, "next": str}`
- status: `200`
- verify: http_status(code=200, path="/api/run/{run_id}/records")
- errors:
  - `400` with detail `not a cursor of this run's records` for a `before` that does not parse.
- verify: json_path(path="$.detail", equals="not a cursor of this run's records")
- code: groom/groom/app.py::run_records@c9a62cda6413
- code: groom/groom/records.py::page@09731cb4c8bf
- detail: [run Activity tab](../concepts/run-activity-tab.md)
- tests: groom/tests/test_records.py::test_the_records_endpoint_serves_a_page_and_refuses_a_bad_cursor
- tests: groom/tests/test_records.py::test_a_page_lists_spans_logs_events_and_alerts_newest_first_with_time_kind_node_and_text
- tests: groom/tests/test_records.py::test_paging_by_the_cursor_loses_and_repeats_no_record
- tests: groom/tests/test_records.py::test_the_last_page_has_no_cursor_and_a_full_page_with_nothing_older_has_none_either
- tests: groom/tests/test_records.py::test_a_page_is_capped_and_a_cursor_that_does_not_parse_is_refused

The route is `GET /api/run/{run_id}/records`, registered by the [groom server](groom.md) and requested through the [serve-run-records](groom.md#serve-run-records) invocation. The path variable `run_id` is the telemetry run id from the run detail payload. The query holds `before`, `limit` and `metrics`, and the request has no required headers and no body.
