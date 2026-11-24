story: SM-01M6CRJQQHA6V1TEMB155R7F2K
date: 2026-11-24
elements: RunDetail, ReadActivityTab
sources: groom/groom/app.py, groom/groom/archive.py, groom/groom/store.py, groom/groom/pools.py, groom/groom/assets/dashboard.js

An operator who reads a run that left the live store wants what happened, not only what it cost. The Activity tab of an archived run uses the timeline, the reading pane, Raw and the search of a live run, and the dashboard's `runApi` alone switches the route from `/api/run/{id}` to `/api/archive/{id}`. A turn read shows 'Reading this turn from the archive…' while it waits.

Each archive read runs on the archive pool, so the live dashboard never waits on it. This keeps `an-archived-run-is-listed-from-the-summary-stored-when-it-was-archived`. The story's phrase 'the query pool' means that pool.

Each read resolves the run by its exact id inside the archive root before it enters the frozen file, because `run_source` falls back to the live store and `archive_dir` falls back to a prefix. A run id that is a prefix, a live run's id or a path answers 404. The read enters `run_source` inside the pooled function, because the pool does not copy the context variable that redirects the reads. A read that finds the file unreadable drops the archive's index, so the next open builds it again.

The turns index stays in groom.db, so the turn query follows the archive being read and takes the rows from the live connection. A gate of an archived run reads its answer as unavailable, because its workspace is gone.

An archive whose files are gone answers 410 on every activity read. The tab then says 'Activity cannot be read' and that the Overview still shows the run's stored summary. The tab does not hide, so the operator learns why it is empty.

A turn that cannot be read says so with a retry and the timeline stays, as it does for a live run. This keeps `a-turn-reads-from-its-own-record`. Raw lists the archive's records newest first, counts the records and the metric samples it hides, and keeps the samples hidden until asked, as `raw-reaches-every-record-and-the-feed-is-gone` says. Transcript text goes through the sanitizer the live run uses.

The http book keeps `an-archive-read-refuses-every-id`: the book's groom archives nothing, so the five activity reads stay declared and unseen. `groom/tests/test_archive_activity.py` and `groom/tests/test_archive_activity_dynamic.py` play them against a real frozen archive.
