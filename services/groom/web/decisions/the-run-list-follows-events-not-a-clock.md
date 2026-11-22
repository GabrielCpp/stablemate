story: none
date: 2026-11-22
elements: Runs
sources: groom/groom/live.py, groom/groom/projection.py::run_row, groom/groom/assets/dashboard.js

The run list changes when groom learns something, not every five seconds. A source marks the fleet dirty, and one flush
a tenth of a second later sends only the rows whose content changed. A run turns silent when a deadline fires at the
moment its silence passes the liveness threshold, because an absence sends no event. The row carries `last_seen_ts`, so
the page counts "silent 4m" itself from its one-second ticker and the server sends nothing while the count grows. A
quiet fleet therefore sends no frame at all.
