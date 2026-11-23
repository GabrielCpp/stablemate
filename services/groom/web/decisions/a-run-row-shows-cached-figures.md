story: SM-01M6CN5PZWE7VS9B8P6QSBK9NF
date: 2026-11-22
elements: Runs
sources: groom/groom/figures.py, groom/groom/app.py, groom/groom/projection.py, groom/groom/assets/dashboard.js

The story asked that every row of the run list show what the run has cost, how long it has been active and how many
items it has done, so the operator compares runs without opening each one.

The figures come from the same store reads as `groom cost` and `groom profile`. The row's cost matches the cost report
and its active time matches the `active` figure of the profile, for one run read at one moment.

The cost carries its coverage as priced turns over all turns. A backend that reports no cost on any turn shows
"no cost reported" in place of a dollar figure, so a missing cost never reads as zero dollars. A run with no finished
node shows "no cost yet" and no item count, and the row fills in when its first node finishes. The narrowed column,
shown while a run is open, keeps every figure and drops the word "priced" to fit.

Items done come from the `progress` label of the latest ended span that carries one. Prose and a total of zero are
ignored. The count carries no noun that names the unit, because the label does not say what the items are.

Groom computes the figures when it first hears from a run and after each committed span batch of that run. The work
runs in the query pool, with one pass running and at most one queued per run, so a burst of batches costs one extra
pass. The fleet push copies the cached figures into each row and reads nothing from the store, so the cost of a push
does not grow with the number of rows. A run groom has not heard from has no figures line.

The order of the list does not depend on the figures.
