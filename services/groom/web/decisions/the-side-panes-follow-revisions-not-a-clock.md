story: none
date: 2026-11-22
elements: Dispatch, History
sources: groom/groom/live.py::bump, groom/groom/state.py, groom/groom/dispatch.py, groom/groom/app.py::_write_summary, groom/groom/assets/dashboard.js

The Dispatch and History panes change when groom learns something, not on a timer. The fleet frames carry a revision
number for each pane, and the same flush that sends the run rows sends it. A change to a dispatch queue or to a run's
history bumps its number. An open pane fetches again, at most once per 300 milliseconds, when its number moves, and a
pane that opens fetches once. A quiet queue and a settled history therefore send no request after the first.
