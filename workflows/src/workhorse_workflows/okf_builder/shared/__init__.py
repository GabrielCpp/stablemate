"""What more than one of okf-builder's machines needs.

The rule that puts a module here is a counting one, not a taste one: `workflow.py` and
each `<flow>/flow.py` own the modules only they reach, and anything a *second* machine
also reaches moves here. That is why the walk's `stack` and `walkthrough` nodes are not
here (only `walkthrough_web/flow.py` calls them) while `worklist` and `checkpoint` are —
the build drains a worklist and so does the walk, against their own.

* `blueprint` — the one `Blueprint` every node in the distribution decorates against
* `paths` — the pure derivations: where a book, a source tree and a worklist are
* `schemas` — the agent-reply models and node return types
* `worklist` — the drain's two primitives: take an item, write back what came of it
* `checkpoint` — the mechanical convergence gate (`ostler fmt` + `doctor`) and its repairs
* `stubs` — the `--dry-run` stand-ins, which have to sit beside neither caller

Nothing here imports a flow or `workflow.py`; the dependency points one way, exactly as it
does from `nodes/` upward.
"""
from __future__ import annotations

from workhorse_workflows.okf_builder.shared.blueprint import blueprint

__all__ = ["blueprint"]
