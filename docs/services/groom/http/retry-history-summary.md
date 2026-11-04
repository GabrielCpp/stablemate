---
type: endpoint
slug: retry-history-summary
title: retry-history-summary
---
# retry-history-summary

- server: [groom server](groom.md)
- method: `POST`
- path: `/api/history/{run_id}/retry`
- does:
  - Puts an archive whose summary could not be read back in the queue of the background read and wakes the worker.
  - Changes nothing for a run that is not an unreadable archive, and answers `ok` false.
  - Does not open the archive or rewrite it.
- response:
  - media: `application/json`
  - body: `{"ok": bool}`
- status: `201`
- verify: json_path(path="$.ok", matches="^(true|false)$")
- errors: none intentionally emitted by this handler.
- code: groom/groom/app.py::history_retry@cf5a69e66cba
- code: groom/groom/history.py::retry@109fc9780a80
- detail: [archived run history](../concepts/archived-run-history.md)
- moves: none, because the retry only queues a read and no state node of the book describes that queue
- tests: groom/tests/test_archive_history.py::test_the_retry_route_puts_an_unreadable_summary_back_in_the_queue
- tests: groom/tests/test_archive_history.py::test_a_retry_changes_nothing_for_a_run_that_is_not_an_unreadable_archive
