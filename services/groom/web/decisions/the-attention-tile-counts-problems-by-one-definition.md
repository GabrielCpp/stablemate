story: SM-01M6CN5WX10DR1FDG38GHFG9KN
date: 2026-11-22
elements: RunDetail
sources: groom/groom/problems.py, groom/groom/figures.py, groom/groom/overview.py, groom/groom/assets/dashboard.js

The operator wanted to read a run's cost, time, items, turns and attention from five tiles, and to trust that the
problem count names the same things the rest of the page shows. Each tile has one definition.

Retries are the agent turns after the first of a visit to a node, so the turns tile and the Retries column of the flow
tree sum to the same number. Sessions are the distinct resume generations of the run, or 1 when it never resumed. A
failed gate check is a gate check span that ended dirty. Gates are the operator waits of the run, and a wait that is
still open counts while it runs.

Problems are failed steps, retries, failed gate checks and churn alerts. An answered gate is not a problem, because the
operator already acted on it. A fired alert lives only in memory, so churn is replayed from the stored spans with the
same rule the alerts use, and the count holds after groom restarts.

Cost per item divides the cost by the finished items, never by the total, and a run with no finished item shows none.
Wall time always sits beside active time, because wall time alone reads as work. An estimate is always labelled, 'at
list price' on a live run and 'estimate: this backend reports no cost' on an ended one.

The just-started pane says only 'No finished work yet' and 'Figures appear when the first node finishes'. The mockup
added 'The first agent turn reports its cost when it ends'. The pane shows no cost until a node finishes, so that line
would promise a figure the pane does not show, and the pane leaves it out.
