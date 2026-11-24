story: SM-01M6CRJ1FHFG7W0J8CRDMS0ZAK
date: 2026-11-23
elements: History
sources: groom/groom/assets/dashboard.js, groom/groom/history.py

An operator who asks what one workflow cost this month used to read the whole list and add it up by hand. History now narrows to the runs they care about, and the totals above the table read those runs alone.

The filters narrow the summaries the page already holds, so each answers at once and makes no request. This keeps `the-run-list-is-filtered-in-the-browser`. The one exception is the range that includes the archives, which reads History again, because the 30 day listing does not carry them, and leaving it reads History again without.

The totals are summed in the browser from the rows shown, with the same clauses the server's totals carry: the estimate, the runs partly priced, the summaries still being read and the summaries that could not be read. The strip never describes a run the table hides. The server's `totals` stay for the terminal client.

The Workflow and Repo choices come from the runs the list holds, so no choice leads to an empty table by itself. The Ending choices come from the `endings` the route returns, one list in the server's order, so a new ending appears with no change to the page.

The text filter matches the run id and repo@branch only, as the mockup's 'Filter by run or repo…' says. The range starts on the last 30 days, the retention window.

Opening a run keeps the filters and turns the table into a narrowed list of the same rows, with a line stating the filters, because the operator chose those rows. Closing the run returns to the table with the filters set, and leaving History for another tab keeps the filters and the open run. This keeps `the-page-has-five-panes`.

When the filters leave nothing, the pane says no runs match these filters and offers Clear the filters, and the totals read zero. The line differs from the one for a History with no run at all, so the operator knows the filters hid the runs.

The elements are declared and not played, because the book's groom holds only pushed runs, which report no telemetry and so never reach History. The browser tests in `groom/tests/test_history_filters_dynamic.py` play them against stored summaries.
