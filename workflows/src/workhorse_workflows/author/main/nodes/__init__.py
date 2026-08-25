"""The non-agent work the **main** author machine sequences, grouped by subject.

Importing this package registers every node on the shared `blueprint`, which is the one
name [`../../workflow.py`](../../workflow.py) needs from here. The submodules are the
subjects:

* `config` — what the run works on, and the branch it works on it in
* `intake` — give every manually entered work bullet a durable id
* `grill` — find the slash command that opens the operator's grilling session
* `epics` — which epic is next
* `stories` — one story at a time: seed it, pick it, validate it, ground it
* `coverage` — whether an epic's stories cover it, and the backlog it consumed
* `artifacts` — the whole-run gates, and the git tail that ships what they passed

The survey graphs' nodes are not here, and they keep a blueprint of their own so a reader
can see which nodes belong to which machine: what both survey flows call is in
[`shared/survey/`](../../shared/survey), and what one of them calls sits beside that flow,
in [`surveyor/nodes/`](../../surveyor/nodes) and
[`parity_surveyor/nodes/`](../../parity_surveyor/nodes).

`epic-edit` and `story-edit` do import from here, and that is not a leak: they edit the
same epics, stories and backlog this machine writes, so the node that validates a story or
adopts a bullet has to be the *same* node or the two would drift. What every flow shares —
survey included — is in [`shared/`](../../shared) instead.

Ported from `base-library/workflows/author/scripts/`. The same three things change as in
`research`, and nothing else does: the JSON envelope on stdout becomes a **returned
model**, the positional `sys.argv` entries become **typed parameters**, and a `sys.exit(1)`
becomes `raise WorkflowFailed(...)`. Two shapes specific to these scripts go with them:

* every `emit(...)` / `done(...)` helper ended in `sys.exit(0)` — an "outputs and stop"
  that only made sense for a subprocess. A node returns its model instead, and the
  *caller* decides whether an unsuccessful result ends the flow;
* the `[script-name]` log prefixes are gone. The run record already names the state that
  logged the line, so the prefix was the engine's job all along.
"""
from __future__ import annotations

from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.main.nodes.artifacts import (
    commit_author,
    open_author_pr,
    validate_artifacts,
    verify_integrity,
    verify_reconcile,
)
from workhorse_workflows.author.main.nodes.config import branch_author, load_config
from workhorse_workflows.author.main.nodes.coverage import prune_backlog, validate_coverage
from workhorse_workflows.author.main.nodes.epics import select_epic, select_epic_document
from workhorse_workflows.author.main.nodes.grill import resolve_grill_trigger
from workhorse_workflows.author.main.nodes.intake import adopt_backlog
from workhorse_workflows.author.main.nodes.stories import (
    check_mockup_needed,
    check_story_feedback,
    check_story_grounding,
    prune_bullet,
    record_attempt,
    remove_story,
    seed_story,
    select_story,
    validate_story,
)

__all__ = [
    "blueprint",
    "adopt_backlog",
    "branch_author",
    "check_mockup_needed",
    "check_story_feedback",
    "check_story_grounding",
    "commit_author",
    "load_config",
    "open_author_pr",
    "prune_backlog",
    "prune_bullet",
    "record_attempt",
    "remove_story",
    "resolve_grill_trigger",
    "seed_story",
    "select_epic",
    "select_epic_document",
    "select_story",
    "validate_artifacts",
    "validate_coverage",
    "validate_story",
    "verify_integrity",
    "verify_reconcile",
]
