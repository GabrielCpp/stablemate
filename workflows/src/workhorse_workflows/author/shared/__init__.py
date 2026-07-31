"""What more than one of author's machines needs.

The rule that puts a module here is a counting one, not a taste one: `workflow.py` and
each `<flow>/flow.py` own the modules only they reach, and anything a *second* machine
also reaches moves here.

* `paths` — the pure derivations: where the backlog, the epics and a survey's records are
* `schemas` — the agent-reply models and node return types, split by machine
* `survey` — the surveyor library: the middle both survey flows walk, plus the `blueprint`
  they register on and the `--dry-run` stand-ins

`survey/` is a package rather than a module because it is a genuinely separate *library*
with a blueprint of its own — the nodes the two survey flows share verbatim
(`select_next_unit`, `mark_unit`, `validate_record`, `verify_records`) and the inventory
they both expand. The nodes only one of them calls live with that flow instead:
`surveyor/nodes/` and `parity_surveyor/nodes/`.

Nothing here imports a flow or `workflow.py`; the dependency points one way.
"""
from __future__ import annotations
