---
type: endpoint
slug: get-run-history
title: get-run-history
---
# get-run-history

- server: [groom server](groom.md)
- method: `GET`
- path: `/api/history`
- does: all
  - Returns the runs that ended in the last 30 days, newest end time first, each as one row of the [run history summary](../concepts/run-history-summary.md), with the [totals](../concepts/run-history-totals.md) of the list and the endings the filters offer.
  - Leaves out every run that is alive, which the server decides from the runs it holds in memory, and lists a finished run while its row is still in Runs.
  - Lists an ended run whose summary is not written yet as a row with `ready` false, carrying only the run, repo, branch and end time.
  - Lists a run with no recorded ending once it has been silent for 48 hours, with the ending `none`.
- verify: json_path(path="$.totals.runs", matches="^[0-9]+$")
- does:
  - Reads the stored summaries on the query pool and scans no run's records, so it opens in under two seconds with the store full.
  - Does not write the telemetry store, mutate workflow state or broadcast a websocket frame.
- response:
  - media: `application/json`
  - body: `{"runs": [{"run_id": str, "workflow": str, "type_hue": int, "repo": str, "branch": str, "ready": bool, "ending": str, "ending_label": str, "ended_ts": float, "active_s": float | null, "wall_s": float | null, "cost_usd": float | null, "est_usd": float | null, "priced_turns": int | null, "turns": int | null, "items_done": int | null, "items_total": int | null, "gates": int | null, "problems": int | null}, ...], "endings": [[str, str], ...], "totals": {"runs": int, "reading": int, "ready": int, "spent_usd": float, "estimate_usd": float, "partly_priced": int, "active_s": float, "success": int}}`. `ending` is one of `success`, `gave-up`, `failed`, `interrupted`, `crashed` or `none`, and `ending_label` is the same ending in words. The figures of a row that is not ready are null. `endings` lists every ending as a key and its words, in the order the [history filters](../concepts/run-history-filters.md) offer them.
- status: `200`
- verify: http_status(code=200, path="/api/history")
- errors: none intentionally emitted by this handler. A failure of the read is a framework-level failure, which the dashboard shows as the failed state of the [history state](../gui/screens/groom-dashboard.md#history-state).
- code: groom/groom/app.py::api_history@b3d9fc46ae77
- code: groom/groom/history.py::listing@931989b4c09b
- detail: [run history summary](../concepts/run-history-summary.md)
- tests: groom/tests/test_history.py::test_the_history_route_lists_the_ended_runs_and_leaves_out_a_run_that_is_alive
- tests: groom/tests/test_history.py::test_the_list_reads_summaries_and_opens_in_under_two_seconds_with_the_store_full
- tests: groom/tests/test_history.py::test_the_listing_names_every_ending_once_in_the_order_the_ending_filter_offers_them
- tests: groom/tests/test_history.py::test_the_list_is_newest_end_time_first_and_stops_at_thirty_days

The route is `GET /api/history`, registered by the [groom server](groom.md) and requested through the [serve-run-history](groom.md#serve-run-history) invocation. The request has no path variable, query, required header or body.
