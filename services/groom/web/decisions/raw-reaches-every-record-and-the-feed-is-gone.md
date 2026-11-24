story: SM-01M6CQJQX2EJRV3A2ZKK6EFH18
date: 2026-11-23
elements: RunDetail, ReadActivity
sources: groom/groom/records.py, groom/groom/store.py, groom/groom/activity.py, groom/groom/assets/dashboard.js

An operator who wants a record the old feed's newest 60 could not reach had to leave the browser for the terminal. The Activity tab now reaches every record of the run, so the old feed and the Details tab can go in the same change.

Raw reads one endpoint that merges spans, logs, turn events and derived churn rows newest first. It pages by a cursor of time, kind and row id, 200 a page, so a record is never lost or repeated across pages and records with the same time keep one order. The old frame's `LOG_TRAIL_LIMIT` no longer bounds what the browser reaches.

A span is one record, written when it ends, with its duration and cost. A start row and an end row doubled every step, and the start carried nothing the end lacks.

Metric samples are off by default and counted either way. They outnumber every other kind and say nothing an operator reads line by line.

Raw says how many records the run has and how many are shown, so a reader knows whether to load older ones. Older records append below and keep the reader's place. While following, a refresh puts new records on top. A pause holds them, and a refresh that finds no overlap with the shown page replaces it.

Raw replaces the timeline and the pane, so the bar keeps only the follow control, Metric samples and Raw, and `j`, `k` and `e` move nothing. Leaving Raw restores the timeline's selection, because Raw never changed it. This keeps `the-timeline-moves-by-keys-and-narrows-by-search` and `the-activity-timeline-follows-a-live-run`.

A failed Raw read says so with a retry and leaves the timeline working. A failed read never reads as an empty run.

Steps and Info logs start off, so the first view is turns, gates, problems and one folded line per run of passing steps. Each shows how many rows it adds across the run. A log at info level or above lands inside the pass it belongs to and never splits a fold, which keeps `the-timeline-groups-by-work-item-pass-and-visit`. A debug log is no timeline row, and Raw lists it.

The Details tab, the feed and its All, Transcript and Telemetry views went in this story, after Raw and the toggles reached everything they did. The `groom.trailView` key is no longer read, so a stale saved view is ignored. Each Details record keeps the new home `the-details-tab-gave-way-to-activity-files-and-diff` names. Its metric cells went: node, in turn, agent idle and last beat sit on the Overview strip, which gained the time in the node and the wait's kind. Uptime gave way to active and wall time, spans to Raw's count and errors to the Problems count. The alert chips gave way to the churn row and the run head.

The no-telemetry words are the Details tab's, split into two sentences where it used a dash.

`GET /worker/{container_id}` keeps its `history` and `metrics` for the terminal client, whose logs and transcript commands are unchanged.

The no-telemetry words are played. A run a push creates holds no span, so opening its Activity tab reads them in place of a timeline, and `ReadActivity` plays that on every state a run takes.

The Steps, Info logs, Raw and Metric samples controls and the Raw elements are declared and not played. The book's groom holds only pushed runs, which report no spans, and its OTLP receivers take protobuf the book cannot write, so the Activity tab has no bar. The browser tests in `groom/tests/test_activity_raw_dynamic.py` play them against real spans.
