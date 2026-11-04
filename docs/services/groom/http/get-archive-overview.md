---
type: endpoint
slug: get-archive-overview
title: get-archive-overview
---
# get-archive-overview

- server: [groom server](groom.md)
- method: `GET`
- path: `/api/archive/{run_id}/overview`
- does: all
  - Reads one archived run's Overview from its frozen archive through `archive.run_source`, entered inside the archive pool's thread, so the live store is never asked about it.
  - Resolves the run by its exact id before it reads anything, and answers `404` when the stored summary is not an archived run's.
  - Returns the body of [get-run-overview](get-run-overview.md) with `archive` set to `ready`, and the ending's moment blanked, because an archive keeps no live clock.
  - Returns `archive` set to `gone` for an archive whose telemetry file is gone.
  - Takes the `figures`, `gates`, `problems`, `compare`, `standing` and `facts` of a `gone` body from the stored summary, with no flows or nodes.
  - Does not rewrite the archive, write the telemetry store or broadcast a websocket frame.
- verify: json_path(path="$.archive", matches="^(ready|gone)$")
- response:
  - media: `application/json`
  - body: `{"archive": "ready" | "gone", "finished": bool, "run_id": str, "figures": {...}, "standing": {...}, "compare": {...} | null, ...}`. A `ready` body also carries the keys of [get-run-overview](get-run-overview.md).
- status: `200`
- verify: http_status(code=200, path="/api/archive/run-1/overview")
- errors: `404` for a run id that is not an archived run.
- verify: json_path(path="$.status_code", equals=404)
- errors: a framework-level `500` for an archive that cannot be opened, which the dashboard shows as a failed Overview with a retry.
- verify: json_path(path="$.status_code", equals=500)
- code: groom/groom/app.py::archive_overview@23db5baa0a48
- code: groom/groom/app.py::_archive_overview@c3bd4430105d
- code: groom/groom/overview.py::stored_overview@085a2ec7726c
- detail: [archived run history](../concepts/archived-run-history.md)
- tests: groom/tests/test_archive_history.py::test_the_archive_route_reads_an_archive_by_its_exact_id_inside_the_pool_thread
- tests: groom/tests/test_archive_history.py::test_the_archive_route_does_not_open_a_run_the_live_store_still_holds
- tests: groom/tests/test_archive_history.py::test_an_archive_whose_telemetry_file_is_gone_answers_from_the_stored_summary
