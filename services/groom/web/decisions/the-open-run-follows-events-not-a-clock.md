story: none
date: 2026-11-22
elements: Runs
sources: groom/groom/live.py, groom/groom/app.py::_follow_transcript, groom/groom/localfs.py, workhorse/workhorse/otel.py::resource_attributes, groom/groom/projection.py::run_detail, groom/groom/assets/dashboard.js

The open run changes when groom learns something, not every five seconds. A source marks the run dirty, and the flush that
sends the changed rows then builds the run's detail and sends it only when it differs from the last one that went out. A
quiet open run therefore receives no detail frame, and a tab that has just opened the run always gets one. Nothing in the
detail counts time: a running turn, the last beat, the uptime and a silent run's label each carry the moment they began, and
the page draws the span from its one-second ticker. The detail carries `activity_rev` and `metrics_rev`, and the Activity
and Raw panes fetch again, at most once per 300 milliseconds, when the number they follow moves. A native run's transcript is
watched on disk while a tab has the run open, so a new line reaches the pane within a second, and the watch ends with the
last tab. When the system refuses the watch or drops it, groom reads the run's newest transcripts every half second
instead, and still sends a detail only when lines arrived.

A container run's sidecar sends a `workspace` frame over its socket when a file under the workspace changes, or when a
checkout's `.git/index` or `.git/HEAD` moves, and sends at most one every two seconds with a trailing one after a burst.
Each frame raises the run's `workspace_rev`, which the detail carries. The Diff and Files panes fetch again, one second
after the number moves, while their tab is open. A pane whose tab is closed fetches again when it opens. An open file in
Files is read again with the list, and the stale marker and Retry stay. A rev of 0 means the sidecar predates the frame,
and the panes load on open and on Retry only. A pushed run has no sidecar, so the book cannot play this rule, and the
page tests cover it.

A native run has no sidecar, and groom reads its Files and Diff from the run's worktree on its own disk. Workhorse names
that worktree as the run's `workspace` when telemetry starts, so groom never walks the checkout that launched the run.
These reads answer with `served: host`, and the panes fetch again when the run's `activity_rev` moves.
