"""The non-agent work only the **main** coder machine calls.

* `pr` — the epic's PR boundary: open it, merge it, escalate when neither can happen

That is the whole package, and the shortness is the point: the coder's main graph is
mostly a sequencer, so nearly every subject it touches is one a sub-flow touches too and
therefore lives in [`shared/`](../../shared). What is left is the one boundary no sub-flow
crosses — an epic's pull request is opened, held against CI and merged by the graph that
owns the epic.

The nodes a sub-graph calls sit beside that graph, in `<flow>/nodes.py` or
`<flow>/nodes/`, and every one of them registers on the same `blueprint`
`shared/blueprint.py` holds, wherever it lives.

**The repo a node works on is a parameter, not the process's cwd.** A driver node has no
per-node working directory, so every node that works on "whichever repo this node was
pointed at" takes a `repo_dir`. That is what makes a multi-repo run legible rather than
positional — and it is how the CI loop's push/poll mismatch became visible at all.
"""
from __future__ import annotations

from workhorse_workflows.coder.main.nodes.pr import (
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
