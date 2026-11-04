---
type: endpoint
slug: get-archive-turn
title: get-archive-turn
---
# get-archive-turn

- server: [groom server](groom.md)
- method: `GET`
- path: `/api/archive/{run_id}/activity/{slug}`
- channel:
- message:
- does: all
  - Reads one agent turn of an archived run from the records the archive kept, on the archive pool.
  - Returns the body of [get-run-turn](get-run-turn.md).
  - Answers `200` with `head.matched` false when the archive holds no record of the turn.
- verify: json_path(path="$.head.slug", equals="001-00001-code")
- emits:
- consumes:
- response:
  - media: `application/json`
  - body: the body of [get-run-turn](get-run-turn.md)
- status: `200`
- verify: http_status(code=200, path="/api/archive/run-1/activity/{slug}")
- errors: `404` for a run id that is not an archived run, or a turn that is not in the archive.
- verify: json_path(path="$.status_code", equals=404)
- errors: `503` when the turn is in the archive but cannot be read, which the dashboard shows with a retry.
- verify: json_path(path="$.detail", equals="the turn could not be read")
- errors: `410` when the archive's files are gone.
- verify: json_path(path="$.status_code", equals=410)
- auth:
- fixture:
- arrange:
- capture:
- code: groom/groom/app.py::archive_turn@39b005fe3641
- code: groom/groom/app.py::_archive_read@ab43be81ebdc
- openapi:
- detail: [archived run history](../concepts/archived-run-history.md)
- observe:
- moves:
- tests: groom/tests/test_archive_activity.py::test_an_archived_run_lists_its_turns_and_reads_one_from_the_records_the_archive_kept
- tests: groom/tests/test_archive_activity.py::test_an_archived_turn_whose_record_is_gone_reads_as_no_record_and_an_unreadable_one_answers_unavailable

