"""The surveyor sub-flow's non-agent work, grouped by subject.

Importing this package registers every node on the shared surveyor `blueprint`, which is
the one name `flows/surveyor.py` needs from here. The submodules are the subjects:

* `config` — where the artifacts live, and whether the planner runs
* `inventory` — materialize the frozen unit list, and correct it locally
* `units` — walk the list: pick the next pending unit, mark one done
* `records` — check one finding record, and check the coverage claim over all of them
* `partition` — the lossless-clustering gate, and the artifacts handed on to author
* `parity` — the parity survey's own two ends: the freeze, and the emitter

The parity surveyor is a second flow over the same middle. It shares `select_next_unit`,
`validate_record`, `mark_unit` and `verify_records` verbatim, so its nodes live here rather
than in a package of their own — one blueprint, two flows selecting from it.

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

from workhorse_workflows.author.nodes.survey._blueprint import blueprint
from workhorse_workflows.author.nodes.survey.config import (
    check_inventory,
    load_survey_config,
)
from workhorse_workflows.author.nodes.survey.inventory import (
    expand_inventory,
    record_slug,
    split_unit,
)
from workhorse_workflows.author.nodes.survey.parity import (
    emit_parity_backlog,
    expand_parity_inventory,
    load_parity_config,
)
from workhorse_workflows.author.nodes.survey.partition import (
    emit_artifacts,
    validate_partition,
)
from workhorse_workflows.author.nodes.survey.records import (
    validate_record,
    verify_records,
)
from workhorse_workflows.author.nodes.survey.units import mark_unit, select_next_unit

__all__ = [
    "blueprint",
    "check_inventory",
    "emit_artifacts",
    "emit_parity_backlog",
    "expand_inventory",
    "expand_parity_inventory",
    "load_parity_config",
    "load_survey_config",
    "mark_unit",
    "record_slug",
    "select_next_unit",
    "split_unit",
    "validate_partition",
    "validate_record",
    "verify_records",
]
