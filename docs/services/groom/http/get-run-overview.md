---
type: endpoint
slug: get-run-overview
title: get-run-overview
---
# get-run-overview

- server: [groom server](groom.md)
- method: `GET`
- path: `/api/run/{run_id}/overview`
- does:
  - Reads one run's stored spans and turn charges and no other run's, so selecting a run does not read the whole telemetry store.
- verify: json_path(path="$.run_id", equals="run-1")
- does:
  - Returns `finished` true when the run has a finished span, and false for a run that has not finished a node.
- verify: json_path(path="$.finished", equals=true)
- does:
  - Returns `cost` with `turns`, `priced_turns`, `reports_cost`, `usd`, `est_usd`, `output_tokens` and `backends`.
- verify: json_path(path="$.cost.priced_turns", equals=2)
- does:
  - Returns `cost.usd` as `null`, never `0`, when no turn of the run reports a cost.
- verify: json_path(path="$.cost.usd", matches="^null$")
- does:
  - Returns `figures`, the five tiles' figures of the [overview tiles](../concepts/overview-tiles.md), with `cost_usd`, `turns`, `active_s`, `wall_s`, `sessions`, `items_done` and `items_total`.
- verify: json_path(path="$.figures.turns", equals=2)
- does:
  - Returns `standing`, with `gates`, `gate_wait_s`, `retries` and `problems`, derived from the run's stored spans.
- verify: json_path(path="$.standing.retries", equals=1)
- does:
  - Returns the [run flow tree](../concepts/run-flow-tree.md) as `flows`, the rows `groom profile` prints.
- verify: json_path(path="$.flows[0].kind", equals="flow")
- does:
  - Returns `nodes`, one row per node merged across flows with `node`, `kind`, `visits`, `time_s`, `mean_s`, `longest_s`, `cost_usd`, `retries` and a `norm` holding the median and its run count, for the [run breakdown views](../concepts/run-breakdown-views.md).
- verify: json_path(path="$.nodes[0].kind", matches="^(agent|step)$")
- does:
  - Returns `norm_runs`, the largest count of comparable successful runs behind any node's median, which is the sample size the By node heading names.
- verify: json_path(path="$.norm_runs", matches="^\\d+$")
- does:
  - Returns `items`, the run's work items with passes, time, cost and outcome, or `null` when the run has no work item.
- verify: json_path(path="$.items", matches="^null$")
- does:
  - Returns `as_of_ts`, the end of the last finished agent turn, which the Overview labels "as of the last finished turn".
- verify: json_path(path="$.as_of_ts", matches="^\\d+(\\.\\d+)?$")
- does:
  - Returns the cost and per-node time that `groom cost` and `groom profile` report for the same run.
- verify: json_path(path="$.cost.usd", equals=2.0)
- does:
  - Reads an archived run's spans from its archive once the run has left the live store.
- does:
  - Does not mutate workflow state, the telemetry store, or any websocket client.
- response:
  - media: `application/json`
  - body: `{"finished": bool, "run_id": str, "cost": {...}, "flows": [{...}, ...], "time_s": {...}, "as_of_ts": float | null}`. An unknown run id returns `finished` false, an empty `flows` and a `cost.usd` of `null`.
- status: `200`
- verify: http_status(code=200, path="/api/run/{run_id}/overview")
- code: groom/groom/app.py::run_overview@1fc6eaf7565a
- tests: groom/tests/test_flows.py::test_the_overview_endpoint_serves_the_same_figures

The route is `GET /api/run/{run_id}/overview`, registered by the [groom server](groom.md) and requested through the [serve-run-overview](groom.md#serve-run-overview) invocation. The path variable `run_id` is the telemetry run id from the run detail payload. The request has no query, no required headers and no body. A failed read of the store is a framework-level `500`, which the dashboard shows as a failed Overview with a retry.
