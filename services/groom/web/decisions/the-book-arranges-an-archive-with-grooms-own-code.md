story: SM-01M6CRJQQHA6V1TEMB155R7F2K
date: 2026-11-24
elements: ReadArchiveActivity, ReadArchiveRecords
sources: groom/groom/archive.py, groom/groom/store.py

The book's groom never receives telemetry, so no run reaches an archive by the way a workflow sends data. The surface seeds each archived run by running groom's own code, `store.insert_spans`, `store.insert_turns` and `archive.archive_run`, in a subprocess with the app's database and home. The files the page reads are then the ones groom writes, and the stored summary row carries the archived mark that History lists. An archive whose files are gone is the same run with its folder removed after the freeze, so the stored summary stays and the telemetry file is missing. Each play names its run with a fresh token, so no journey depends on another's archive.
