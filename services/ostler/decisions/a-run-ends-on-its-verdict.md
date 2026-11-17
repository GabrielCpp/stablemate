story: none
date: 2026-11-17
elements: RunBook
sources: ostler/ostler/book/progress.py, ostler/ostler/book/cli.py::cmd_run

`ostler book run` says two things besides the journeys it prints. While it plays it writes one flushed line to standard
error as each journey ends (`[at/total] name verdict seconds`) and as the cells, the input classes and the witness start
and end. A person or a watcher sees that a long run is alive without waiting for its report.

The run then ends its standard output with a verdict block. The block opens with the word `verdict`, then the counts of
the journeys, then `green` or `red:` with the parts that made the exit non-zero (journeys, cells, inputs, underspecified
inputs, stale register, divergences never met, known defects never met, witness), then one `FAIL` line for each failing
journey, at most 50, and a line counting the rest. The exit is 1 exactly when `red:` names a part, so the last lines of a
run say why it failed without a read of the whole report.

The sandbox plays `RunBook` on the small book `demo`, which is green, so the book sees the block's `green` and exit 0 and
never the `red:` or `FAIL` lines. The progress lines go to standard error, which the book does not compare for this
command.
