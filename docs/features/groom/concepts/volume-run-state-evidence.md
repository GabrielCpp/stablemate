---
type: concept
slug: volume-run-state-evidence
title: Volume run-state evidence
---
# Volume run-state evidence

Discovery volume reconstruction reads both files from the latest run directory;
they are complementary evidence, not interchangeable implementations. The
checkpoint object supplies the current graph-node value, while the metadata
object supplies the terminal marker. A readable checkpoint cannot establish
whether the run finished, and readable metadata cannot establish its current
node.

`_current_run_state` lists run directories once, selects the final directory,
then reads `checkpoint.json` into the first element of its result and
`run.json` into the second. It returns empty strings independently when either
file is absent or has no usable value. The source records no preference between
the formats because each answers a different part of the state tuple.

- code: groom/groom/discovery.py::_current_run_state
- rule: for discovery volume reconstruction, read sidecar run checkpoint data for `current_node` and sidecar run metadata for `terminal`; neither format substitutes for the other
