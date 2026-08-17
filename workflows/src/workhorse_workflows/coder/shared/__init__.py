"""What more than one of the coder's machines needs.

The rule that puts a module here is a counting one, not a taste one: `workflow.py` and
each `<flow>/flow.py` own the modules only they reach, and anything a *second* machine
also reaches moves here. That is why `pr` is not here (only the main graph opens and
merges the epic's PR) and `dream`'s two nodes are not (only `dream/flow.py` runs them),
while `story` is — seven of the nine graphs start by turning a slug into paths.

The plumbing every graph stands on:

* `blueprint` — the one `Blueprint` every node in the distribution decorates against
* `paths` — the pure derivations the YAML's scripts each carried a private copy of
* `schemas` — the agent-reply models and node return types
* `stubs` — the `--dry-run` stand-ins, which have to sit beside neither caller
* `contract` — the assertions `genesis` has to *establish* and the main loop *assumes*,
  in one implementation so the two cannot drift apart silently
* `qa_support` — the run-log parse and routing notes the QA nodes need around an
  `Ostler` call, which answers in `QaOutcome` and needs no adapter of its own
* `story_status` — how a story's state is read back off disk

The node subjects a second graph runs:

* `story` — the spine every per-story flow starts with: slug → paths, workspace, stamping
* `dev` — planning's gates and the per-service implementation loop
* `queue` — the main graph's spine: which epic, which story, on what branch, what it recorded
* `backlog` — file separate-scope discoveries out to the author, and drain them back in
* `ci` — the post-PR loop: poll Actions, hand a failure to a fixer, push, poll again
* `docs` — is there an OKF book, how can its diff be read, and does the update hold
* `okf` — the diff-to-OKF obligation packet
* `review` — where a review runs, what its findings settled to, what a human dropped in

`docs`, `okf` and `review` keep the name of the subject rather than of the flow that reads
them most, because each is reached by two graphs: naming `docs` after `docs/` would be the
mirroring this layout exists to undo. Nothing here imports a flow or `workflow.py`; the
dependency points one way.
"""
from __future__ import annotations

from workhorse_workflows.coder.shared.blueprint import blueprint

__all__ = ["blueprint"]
