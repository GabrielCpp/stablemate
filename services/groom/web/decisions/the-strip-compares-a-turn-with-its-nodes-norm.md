story: SM-01M6CN5T0JGN103Q535D0KC2GX
date: 2026-11-22
elements: RunDetail
sources: groom/groom/store.py, groom/groom/norms.py, groom/groom/projection.py, groom/groom/app.py, groom/groom/assets/dashboard.js

The operator wanted to see whether the turn a live run is in lasts longer than usual. The strip above the Overview
compares the current turn or step with the norm of its node.

The norm is the median length of a turn, or of a step, at one node across successful runs of the same workflow. A run is
one trace, because a run id repeats across executions. A run is successful when its root span ended with
`workhorse.terminal` equal to `terminal`. Failed, interrupted and other-workflow runs never move the norm. A run whose
visit to the node ran agent turns gives that node no step sample.

Under five comparable runs the strip shows no median, only the count: "no norm yet: N comparable runs". A wait shows the
time waited and has no norm. An agent node between turns keeps the turn norm and never says "longer than usual". A node
with no finished visit anywhere says so instead of guessing a kind.

Groom reads the norm through the query pool when a watched run first reports a node or moves to a new one. The read goes
through the `spans_node` index and never scans the whole store. The strip builder reads only the cache, so rendering the
strip causes no read of the store.

A turn or step past its norm reads "longer than usual" in words as well as in the warning color, so a reader who does not
see color gets the same signal.

How a norm change refreshes an open pane is in `the-overview-refreshes-on-a-committed-span-batch`.
