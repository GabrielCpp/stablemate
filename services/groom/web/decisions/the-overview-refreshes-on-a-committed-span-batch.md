story: SM-01M6CN5KZ826G63H89XZGBREEW
date: 2026-11-22
elements: RunDetail
sources: groom/groom/assets/dashboard.js, groom/groom/app.py, groom/groom/live_history.py, groom/groom/norms.py

The story asked that the open Overview follow the run without the operator reloading it. The page now fetches the
Overview again when the run's figures revision moves, and a committed span batch of the run is the only data trigger.
The revision rises once per committed batch while a pane is open on the run. A metric or a log line moves the strip and
the running mark, and it never moves the figures.

A norm change moves the revision of the runs of its own workflow and no other. A pane for a run of one workflow does
not refetch because another workflow's norm changed.

The refresh happens in place. The page keeps the old figures on screen until the new ones arrive and sets no busy
state, so the tiles and the tree neither blank nor flash. The scroll position, the chosen view and sort and every
expanded or collapsed row survive it. A top-level flow that appears during a refresh arrives collapsed.

The time since the last finished turn counts up in the browser from a timestamp, once a second. No timer asks the server
for anything, and an open Overview with no new telemetry causes no read of the store. A run with no open pane causes no
extra read when its telemetry arrives. The run list rows keep their own figures, which belong to the run list.

The running mark follows the metrics. A finished node loses it when its active gauge drops, and the next node gains it
when its gauge rises.

No live region wraps the figures. A screen reader hears no announcement for each change of cost or time.
