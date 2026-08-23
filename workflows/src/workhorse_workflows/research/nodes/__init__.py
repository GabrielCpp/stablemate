"""The research workflow's non-agent work, grouped by subject.

Importing this package registers every node on the shared `blueprint`, which is the one
name `workflow.py` needs from here. The submodules are the subjects, one each:

* `setup` — get a working tree (`clone_repo`)
* `program` — which program, what its manifest says, and what its budget ledger has
  already spent (`load_program`, `record_spend`)
* `measure` — run the experiment outside the agent turn and classify what came back,
  with no model calls (`check_envelope`, `submit_job`, `dry_run`, `watch_job`,
  `collect_job`, `kill_job`)
* `publish` — get the gate's work off this machine (`publish_results`)

Ported from `base-library/workflows/research/scripts/{setup,load_config,publish}.py`.
Three things change and nothing else does:

* the JSON envelope on stdout becomes a **returned model** — a node is a function, so
  its result needs no serialization round-trip to reach the caller;
* the positional `sys.argv` entries become **typed parameters**, checked at the
  callsite by `inspect.signature` rather than by index;
* `sys.exit(1)` becomes `raise WorkflowFailed(...)`, which the driver records as the
  run's terminal state instead of killing the interpreter under it.

The **environment** reads are gone (`AGENT_REPO_DIR`, `REPO_URL`, `REPO_BRANCH`,
`RESEARCH_PROGRAM`, `AGENT_LAUNCH_DIR`, …). They were the operator contract a compose
file, a Makefile and a container entrypoint all wrote to; they are now workflow
parameters of the same names (`repo_dir`, `repo_url`, `repo_branch`, `program`,
`launch_dir`), so a launcher says the same thing with `--params` and the run's inputs
land in the checkpoint. See the rule in `workflows/README.md`.
"""
from __future__ import annotations

from workhorse_workflows.research.nodes._blueprint import blueprint
from workhorse_workflows.research.nodes.measure import (
    check_envelope,
    classify_fault,
    collect_job,
    dry_run,
    job_dir_for,
    kill_job,
    submit_job,
    watch_job,
)
from workhorse_workflows.research.nodes.program import load_program, record_spend
from workhorse_workflows.research.nodes.publish import publish_results
from workhorse_workflows.research.nodes.setup import clone_repo

__all__ = [
    "blueprint",
    "check_envelope",
    "classify_fault",
    "clone_repo",
    "collect_job",
    "dry_run",
    "job_dir_for",
    "kill_job",
    "load_program",
    "publish_results",
    "record_spend",
    "submit_job",
    "watch_job",
]
