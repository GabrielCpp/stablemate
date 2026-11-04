---
type: endpoint
slug: get-archive-records
title: get-archive-records
---
# get-archive-records

- server: [groom server](groom.md)
- method: `GET`
- path: `/api/archive/{run_id}/records`
- channel:
- message:
- does: all
  - Reads one page of an archived run's stored records, newest first, from the cursor a previous page returned, on the archive pool.
  - Returns the body of [get-run-records](get-run-records.md).
  - Hides metric samples and counts them in `metric_samples` until `metrics=1` asks for them.
- verify: json_path(path="$.total", matches="^[0-9]+$")
- emits:
- consumes:
- response:
  - media: `application/json`
  - body: the body of [get-run-records](get-run-records.md)
- status: `200`
- verify: http_status(code=200, path="/api/archive/run-1/records")
- errors: `400` for a cursor that is not one of this run's records.
- verify: json_path(path="$.detail", equals="not a cursor of this run's records")
- errors: `404` for a run id that is not an archived run.
- verify: json_path(path="$.status_code", equals=404)
- errors: `410` when the archive's files are gone.
- verify: json_path(path="$.status_code", equals=410)
- auth:
- fixture:
- arrange:
- capture:
- code: groom/groom/app.py::archive_records@41d94c74047e
- code: groom/groom/app.py::_archive_read@ab43be81ebdc
- openapi:
- detail: [archived run history](../concepts/archived-run-history.md)
- observe:
- moves:
- tests: groom/tests/test_archive_activity.py::test_archive_records_list_newest_first_hide_metric_samples_until_asked_and_page_older_ones
- tests: groom/tests/test_archive_activity.py::test_an_archive_whose_files_are_gone_answers_gone_on_every_activity_route

