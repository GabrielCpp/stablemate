"""The coder workflow's non-agent work, grouped by subject.

Importing this package registers every node on the shared `blueprint`, which is the one
name `workflow.py` needs from here. The submodules are the subjects:

* `genesis` — turn a directory into a repo the author and coder can both stand on
* `dream` — digest a finished run's process record, and drain reflection into a ledger
* `ci` — the post-PR loop: poll Actions, hand a failure to a fixer, push, poll again

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

from workhorse_workflows.coder.nodes._blueprint import blueprint
from workhorse_workflows.coder.nodes.ci import (
    poll_pr_checks,
    push_ci_fix,
    push_epic_branch,
    resolve_ci_workspace,
    select_ci_repo,
)
from workhorse_workflows.coder.nodes.dream import gather_run_evidence, record_improvements
from workhorse_workflows.coder.nodes.genesis import (
    genesis_git_init,
    init_skeleton,
    install_farrier,
    resolve_genesis_target,
    validate_genesis,
    write_agents_yml,
)

__all__ = [
    "blueprint",
    "gather_run_evidence",
    "genesis_git_init",
    "init_skeleton",
    "install_farrier",
    "poll_pr_checks",
    "push_ci_fix",
    "push_epic_branch",
    "record_improvements",
    "resolve_ci_workspace",
    "resolve_genesis_target",
    "select_ci_repo",
    "validate_genesis",
    "write_agents_yml",
]
