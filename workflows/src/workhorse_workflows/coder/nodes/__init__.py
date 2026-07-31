"""The non-agent work only the **main** coder machine calls.

* `pr` — the epic's PR boundary: open it, merge it, escalate when neither can happen

That is the whole package, and the shortness is the point: the coder's main graph is
mostly a sequencer, so nearly every subject it touches is one a sub-flow touches too and
therefore lives in [`shared/`](../shared). What is left is the one boundary no sub-flow
crosses — an epic's pull request is opened, held against CI and merged by the graph that
owns the epic.

The nodes a sub-graph calls sit beside that graph, in `<flow>/nodes.py` or
`<flow>/nodes/`, and every one of them registers on the same `blueprint`
`shared/blueprint.py` holds, wherever it lives.

Ported from `base-library/workflows/coder/scripts/`. The same three things change as in
`research` and `author`, and nothing else does: the JSON envelope on stdout becomes a
**returned model**, the positional `sys.argv` entries become **typed parameters**, and a
`sys.exit(1)` becomes `raise WorkflowFailed(...)`. Two shapes specific to these scripts go
with them:

* every `emit(...)` / `done(...)` helper ended in `sys.exit(0)` — an "outputs and stop"
  that only made sense for a subprocess. A node returns its model instead, and the
  *caller* decides whether an unsuccessful result ends the flow;
* the `[script-name]` log prefixes are gone. The run record already names the state that
  logged the line, so the prefix was the engine's job all along.

One thing changes here that did not change in the earlier two ports. **The repo a node
works on is a parameter, not the process's cwd.** Most of the coder's YAML nodes carried a
`cwd:` and resolved paths against it; a driver node has no per-node cwd, so every node that
worked on "whichever repo this node was pointed at" takes a `repo_dir` instead. That is
what makes a multi-repo run legible rather than positional — and it is how the CI loop's
push/poll mismatch (recorded in the progress ledger) became visible at all.
"""
from __future__ import annotations

from workhorse_workflows.coder.nodes.pr import (
    flag_ci_failure,
    flag_merge_failure,
    merge_pr,
    open_pr,
    open_story_pr,
)

__all__ = [
    "flag_ci_failure",
    "flag_merge_failure",
    "merge_pr",
    "open_pr",
    "open_story_pr",
]
