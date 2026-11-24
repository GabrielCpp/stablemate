story: SM-01M6CRJJDH5VSBZD81RHHR1X4F
date: 2026-11-24
elements: History, RunDetail
sources: groom/groom/archive.py, groom/groom/history.py, groom/groom/overview.py, groom/groom/app.py, groom/groom/pools.py, groom/groom/assets/dashboard.js

An operator who wants to look back at a run that left the thirty-day window chooses Everything, archives included, and finds that run listed with its figures. The run's rows left the telemetry store when the archive froze it, so the list cannot be built from the store.

The archive step computes the run's summary while the run still has its rows, stores it in the archive's manifest and copies it into the stored summary table as an archived row. The list reads the same rows for an archived run as for a run still in the store, opens no telemetry file per row and reads no archive. The word 'archived' marks the row, in the table and in the narrowed list, so the marker never rests on a color.

An archive frozen before summaries existed has a manifest with no summary. Discovery lists it at once from its folder name and manifest as 'reading its summary', with a dash in every figure cell, and the totals count it as still being read. One background read on the archive pool fills the row in, once, and the page shows the figures with no reload. Later visits list the stored row and read nothing. The frozen file is never rewritten, by the read, by an open or by the sweep, and retention and the sweep stay as they were.

An unreadable summary keeps its row with no figures and says 'could not be read' in place of the ending. The table offers Retry now, which asks the background read again and does not open the run. The narrowed list offers none, because the table is where the operator retries.

The Overview of an archive reads the frozen file through the same terminal queries as an ended run, so its cost and its times per node and per flow equal what `groom cost` and `groom profile` report. The route resolves the run by its exact id inside the pooled read, because the read falls back to the live store and the archive lookup falls back to a prefix match. Archive reads have a pool of their own, so the live dashboard never waits on one. The first open builds an index beside the file and says it is reading, with no problem count, since the figures are not there yet. A later open finds the index and shows the Overview in under two seconds.

When the files are gone, the row stays and the detail says 'This archive's files are gone'. Its tiles and facts come from the stored summary and it shows no breakdown. An archive that cannot be opened says so in the detail with Retry now, and the list stays.

An archive has an Overview and an Activity tab and no Files or Diff tab, because its checkout is gone. The story's criterion 'no Activity tab yet' deferred Activity to `read-the-activity-of-an-archived-run`, which is built, so the tab stays.

The elements are declared and not played, because the book's groom archives nothing, since it holds only pushed runs, which report no telemetry. The browser tests in `groom/tests/test_history_archives_dynamic.py` and the tests in `groom/tests/test_archive_history.py` play them against real archives.
