---
type: endpoint
slug: get-archive-activity
title: get-archive-activity
---
# get-archive-activity

- server: [groom server](groom.md)
- method: `GET`
- path: `/api/archive/{run_id}/activity`
- channel:
- message:
- does: all
  - Reads one archived run's turns and timeline items from its frozen archive on the archive pool, so a slow read never blocks the live dashboard.
  - Resolves the run by its exact id inside the archive root and reads nothing else.
  - Returns the body of [get-run-activity](get-run-activity.md), with no live rows, no standing and no running turn.
  - Takes `logs`, and `logs=1` places each info log line among the entries of its pass.
- verify: json_path(path="$.rows[0].slug", matches="^\\d{3}-\\d{5}-")
- emits:
- consumes:
- response:
  - media: `application/json`
  - body: the body of [get-run-activity](get-run-activity.md)
- status: `200`
- verify: http_status(code=200, path="/api/archive/run-1/activity")
- errors: `404` for a run id that is not an archived run.
- verify: json_path(path="$.status_code", equals=404)
- errors: `410` when the archive's files are gone, which the dashboard shows as "Activity cannot be read".
- verify: json_path(path="$.status_code", equals=410)
- auth:
- fixture:
- arrange:
- capture:
- code: groom/groom/app.py::archive_activity@ed9352e9bfa9
- code: groom/groom/app.py::_archive_read@ab43be81ebdc
- openapi:
- detail: [archived run history](../concepts/archived-run-history.md)
- observe:
- moves:
- tests: groom/tests/test_archive_activity.py::test_the_archive_activity_routes_resolve_an_archive_by_its_exact_id_and_nothing_else
- tests: groom/tests/test_archive_activity.py::test_an_archived_run_lists_its_turns_and_reads_one_from_the_records_the_archive_kept
- tests: groom/tests/test_archive_activity.py::test_an_archive_whose_files_are_gone_answers_gone_on_every_activity_route
- tests: groom/tests/test_archive_activity.py::test_an_archive_read_holds_an_archive_pool_worker_and_leaves_the_query_pool_free

