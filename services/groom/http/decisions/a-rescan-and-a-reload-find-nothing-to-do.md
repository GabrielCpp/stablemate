story: none
date: 2026-11-17
elements: Refresh, Reload, RetryHistory
sources: groom/groom/app.py::refresh, groom/groom/app.py::reload, groom/groom/app.py::history_retry

A rescan finds the workflows docker and the run directories list, and the book's groom runs with a docker that always
fails and no run on disk, so it finds none and prunes none. A reload tells the sidecars that are connected, and none
is. A retry asks for an archive's unreadable summary to be read again, and no archive exists. Each says ok and the
count of what it did, which is nothing, or {ok: false} for the retry.
