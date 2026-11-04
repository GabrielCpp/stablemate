---
type: endpoint
slug: get-archive-entry
title: get-archive-entry
---
# get-archive-entry

- server: [groom server](groom.md)
- method: `GET`
- path: `/api/archive/{run_id}/entry/{key}`
- channel:
- message:
- does: all
  - Reads one step, gate, backend retry or churn alert of an archived run in full, on the archive pool.
  - Returns the body of [get-run-entry](get-run-entry.md).
  - Reads a gate's answer as unavailable, because the archived run's workspace is gone.
- verify: json_path(path="$.kind", matches="^(step|gate|retry|churn)$")
- emits:
- consumes:
- response:
  - media: `application/json`
  - body: the body of [get-run-entry](get-run-entry.md)
- status: `200`
- verify: http_status(code=200, path="/api/archive/run-1/entry/{key}")
- errors: `404` for a run id that is not an archived run, or an entry key that is not in the archive.
- verify: json_path(path="$.status_code", equals=404)
- errors: `410` when the archive's files are gone.
- verify: json_path(path="$.status_code", equals=410)
- auth:
- fixture:
- arrange:
- capture:
- code: groom/groom/app.py::archive_entry@2854ca4b72c6
- code: groom/groom/app.py::_archive_read@ab43be81ebdc
- openapi:
- detail: [archived run history](../concepts/archived-run-history.md)
- observe:
- moves:
- tests: groom/tests/test_archive_activity.py::test_the_archive_activity_routes_resolve_an_archive_by_its_exact_id_and_nothing_else
- tests: groom/tests/test_archive_activity.py::test_an_archive_whose_files_are_gone_answers_gone_on_every_activity_route

