story: none
date: 2026-11-22
elements: Runs
sources: groom/groom/live.py, groom/groom/app.py::_follow_transcript, groom/groom/projection.py::run_detail, groom/groom/assets/dashboard.js

The open run changes when groom learns something, not every five seconds. A source marks the run dirty, and the flush that
sends the changed rows then builds the run's detail and sends it only when it differs from the last one that went out. A
quiet open run therefore receives no detail frame, and a tab that has just opened the run always gets one. Nothing in the
detail counts time: a running turn, the last beat, the uptime and a silent run's label each carry the moment they began, and
the page draws the span from its one-second ticker. The detail carries `activity_rev` and `metrics_rev`, and the Activity
and Raw panes fetch again, at most once per 300 milliseconds, when the number they follow moves. A native run's transcript is
watched on disk while a tab has the run open, so a new line reaches the pane within a second, and the watch ends with the
last tab.
