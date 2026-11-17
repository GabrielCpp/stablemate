story: none
date: 2026-11-17
elements: ReadArchiveOverview, ReadArchiveActivity, ReadArchiveRecords, SearchArchive, ReadArchiveEntry, ReadArchiveTurn
sources: groom/groom/app.py::archive_overview, groom/groom/app.py::_archive_read, groom/groom/history.py::stored

A run is archived once groom holds its telemetry and has frozen it. The book never sends telemetry, so no run it
names is archived, and every archive read answers 404 "no archived run <id>". The book keeps that one refusal as a
rule that is always broken and leaves the archive that exists (a 200, or a 410 when its files are gone) as declared
and unseen. The six reads share one action because they refuse alike.
