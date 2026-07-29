"""The research workflow's non-agent work, grouped by subject.

Importing this package registers every node on the shared `blueprint`, which is the one
name `workflow.py` needs from here. The submodules are the subjects, one each:

* `setup` — get a working tree (`clone_repo`)
* `program` — which program, and what its manifest says (`load_program`)
* `publish` — get the gate's work off this machine (`publish_results`)

Ported from `base-library/workflows/research/scripts/{setup,load_config,publish}.py`.
Three things change and nothing else does:

* the JSON envelope on stdout becomes a **returned model** — a node is a function, so
  its result needs no serialization round-trip to reach the caller;
* the positional `sys.argv` entries become **typed parameters**, checked at the
  callsite by `inspect.signature` rather than by index;
* `sys.exit(1)` becomes `raise WorkflowFailed(...)`, which the driver records as the
  run's terminal state instead of killing the interpreter under it.

The **environment** reads stay verbatim (`AGENT_REPO_DIR`, `REPO_URL`, `REPO_BRANCH`,
`RESEARCH_PROGRAM`, `AGENT_LAUNCH_DIR`, …): they are the operator contract that a
compose file, a Makefile and a container entrypoint all write to, and rewriting them
would break every launcher for no gain.
"""
from __future__ import annotations

from workhorse_workflows.research.nodes._blueprint import blueprint
from workhorse_workflows.research.nodes.program import load_program
from workhorse_workflows.research.nodes.publish import publish_results
from workhorse_workflows.research.nodes.setup import clone_repo

__all__ = ["blueprint", "clone_repo", "load_program", "publish_results"]
