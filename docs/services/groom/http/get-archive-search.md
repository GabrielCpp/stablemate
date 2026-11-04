---
type: endpoint
slug: get-archive-search
title: get-archive-search
---
# get-archive-search

- server: [groom server](groom.md)
- method: `GET`
- path: `/api/archive/{run_id}/search`
- channel:
- message:
- does: all
  - Finds the turns of one archived run whose transcript says the query, each with its first matching line, on the archive pool.
  - Returns the body of [get-run-search](get-run-search.md).
- verify: json_path(path="$.matches", matches="^\\[")
- emits:
- consumes:
- response:
  - media: `application/json`
  - body: the body of [get-run-search](get-run-search.md)
- status: `200`
- verify: http_status(code=200, path="/api/archive/run-1/search")
- errors: `503` when the transcripts cannot be searched.
- verify: json_path(path="$.detail", equals="the transcripts could not be searched")
- errors: `404` for a run id that is not an archived run.
- verify: json_path(path="$.status_code", equals=404)
- errors: `410` when the archive's files are gone.
- verify: json_path(path="$.status_code", equals=410)
- auth:
- fixture:
- arrange:
- capture:
- code: groom/groom/app.py::archive_search@51af89e10ff4
- code: groom/groom/app.py::_archive_read@ab43be81ebdc
- openapi:
- detail: [archived run history](../concepts/archived-run-history.md)
- observe:
- moves:
- tests: groom/tests/test_archive_activity.py::test_archive_search_matches_the_transcripts_of_an_archived_run
- tests: groom/tests/test_archive_activity.py::test_an_archive_whose_files_are_gone_answers_gone_on_every_activity_route

