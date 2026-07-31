"""The surveyor library: the middle both survey flows walk.

Importing this package registers its nodes on the survey `blueprint` — a second blueprint,
separate from the one author's own nodes use, and the one name `workflow.py` needs from
here so a run of either flow can resolve them. The submodules are the subjects:

* `inventory` — materialize the frozen unit list, and correct it locally
* `units` — walk the list: pick the next pending unit, mark one done
* `records` — check one finding record, and check the coverage claim over all of them

The parity surveyor is a second flow over this same middle. It shares `select_next_unit`,
`validate_record`, `mark_unit` and `verify_records` verbatim, which is what makes them
shared rather than either flow's — one blueprint, two flows selecting from it. What only
*one* flow calls is not here: the survey's `config`/`partition` nodes live in
[`surveyor/nodes/`](../../surveyor/nodes), parity's freeze and emitter in
[`parity_surveyor/nodes/`](../../parity_surveyor/nodes). They register on this blueprint
all the same.

Ported from `base-library/workflows/author/surveyor/scripts/`. The same three things
change as in `research`, and nothing else does: the JSON envelope on stdout becomes a
**returned model**, the positional `sys.argv` entries become **typed parameters**, and a
`sys.exit(1)` becomes `raise WorkflowFailed(...)`. Two shapes specific to these scripts
go with them:

* every `emit(...)` helper ended in `sys.exit(0)` — an "outputs and stop" that only made
  sense for a subprocess. A node returns its model instead, and the *caller* decides
  whether an unsuccessful result ends the flow;
* every `try: import yaml / except ImportError` degradation branch is gone, along with
  the "PyYAML is unavailable" verdicts they emitted. The library's own rule is a
  top-level import with no fallback, because a gate that answers "I could not load the
  parser, so — clean" is the failure mode that rule exists to make impossible.
"""
from __future__ import annotations

from workhorse_workflows.author.shared.survey.blueprint import blueprint
from workhorse_workflows.author.shared.survey.inventory import (
    expand_inventory,
    record_slug,
    split_unit,
)
from workhorse_workflows.author.shared.survey.records import validate_record, verify_records
from workhorse_workflows.author.shared.survey.units import mark_unit, select_next_unit

__all__ = [
    "blueprint",
    "expand_inventory",
    "mark_unit",
    "record_slug",
    "select_next_unit",
    "split_unit",
    "validate_record",
    "verify_records",
]
