story: SM-01M6CRJCCQMV38ZHX44NT0WG84
date: 2026-11-24
elements: History, RunDetail
sources: groom/groom/medians.py, groom/groom/history.py, groom/groom/overview.py, groom/groom/assets/dashboard.js

An operator who sees a run cost $14 cannot tell whether that is high. The History table, its totals, the Work items tile and By node now put each ended run beside the median of its workflow.

The yardstick is the cost per finished item, because runs of one workflow finish different numbers of items and a total cost would compare a small run with a large one.

A comparable run ended in success, reports a cost with at least one priced turn, finished an item and is not alive. A run that continued after its summary has no end time and stays out. An estimate stays out and shows no comparison, because a list price is no measured cost. A partly priced run stays in with the cost it reports, because most runs are partly priced and leaving them out would empty the pool.

Every count beside a median says comparable, not successful. The strip already reads 'N of M ended in success', and a second count under the same word would contradict it. The title of each count defines the word.

The median leaves out the run it judges, so a run does not move its own yardstick. The tile says 'other', which is why it reads one less than the totals. Five other runs are the floor, as `the-strip-compares-a-turn-with-its-nodes-norm` settled for the norm. Under five the table cell shows the cost per item with no difference, and the tile says how many exist and that it takes five.

The pool is every summary of the workflow, in the store and the archives, whatever the filters and the range. It is read from `run_summary` alone, so the table opens in under two seconds and no telemetry file is opened. The medians arrive with the list, so a filter makes no request. This keeps `history-is-filtered-in-the-browser-and-the-totals-follow`.

A run that did not end in success is not compared anywhere. Its table cell, its tile and its By node show no comparison, and the tile says it was not compared and why.

By node of an ended run reads the medians of per-run node means from the stored summaries, so it holds for an archived run with no span scan. This overturns the norm cache as the source of the By node median in `the-breakdown-traces-cost-to-a-node-or-a-work-item`, for ended runs only. The live strip and the By node of a live run keep the norm, so the two figures may differ for a node. An ended run's cell is a bare signed percent in plain ink so it agrees with the History column.

A difference is a signed percent with a true minus sign and never a color alone.

The elements are declared and not played, because the book's groom holds only pushed runs, which report no telemetry and so never reach History. The tests in `groom/tests/test_medians.py` and `groom/tests/test_history_median_dynamic.py` play them against stored summaries.
