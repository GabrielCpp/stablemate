story: none
date: 2026-11-17
elements: ReadOverview, ReadActivity, ReadRecords, SearchRun, ReadEntry, ReadTurn, ReadHistory, ReadLive, ReadRepos
sources: groom/groom/overview.py::run_overview, groom/groom/activity.py, groom/groom/records.py::page, groom/groom/history.py::listing, groom/groom/alerts.py::live_status

groom reads a run's cost, turns, records, history and live rows from the telemetry it stored, and a workflow sends
that over OTLP as protobuf. The book sends groom only pushes, so its groom has an empty store. Each read then says
what an empty store says: an overview of zeros, no turns, no records, no matches, no history, no live row. A step or
turn key is unknown, so reading it is a 404. The fields that need a stored value are declared unseen with that reason.

A records cursor is checked before the store is read: it is empty, or three parts apart by bars. Any other text is
refused with 400, whether the run exists or not.
