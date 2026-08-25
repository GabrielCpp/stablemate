"""The coder workflow as a Python state machine.

The port of `base-library/workflows/coder/workflow.yaml` — 4,366 lines of YAML, 308
nodes across nine graphs, and the largest thing in the base library by a wide margin. It
builds an epic: it walks the epic queue, and for each story plans, implements, reviews,
documents and QAs it, then commits, opens one PR per epic, holds it against CI, and
merges.

The package has the layout `workflows/README.md` prescribes for every workflow — one
directory per *machine*, so a reader can tell which nodes belong to which graph without
reading either:

* `workflow.py` — the composition root, and only that: the `Registry`, the flow table,
  the dry-run stubs and the console-script binding
* `main/` — the machine a bare `workhorse-coder run` starts, laid out as a flow package
  like the other eight: `flow.py` holds the `Coder` class, and `main/nodes/` the non-agent
  work only that machine calls — `pr` alone, because the epic's PR boundary is the one
  subject no sub-flow touches
* `dev/`, `docs/`, `dream/`, `fix/`, `fix_ci/`, `genesis/`, `qa/`, `review/` — one
  directory per registered Python sub-flow: each `flow.py` beside the `nodes/` and
  `prompts/` only it calls
* `shared/` — what a second machine also reaches: `paths`, `schemas`, `contract`,
  `blueprint`, `stubs`, and the node subjects more than one graph runs (`story`, `dev`,
  `queue`, `backlog`, `ci`, `docs`, `okf`, `review`)

Every agent turn's Markdown lives in the `prompts/` of the flow that renders it, and a
prompt two flows both render is **two files** — `implement-plan.md` exists under `main/`,
`dev/` and `fix/`, each free to diverge. Paths are written from this package root down
(`dev/prompts/implement-plan.md`), because that root is what `workflow.py` declares as
the registry's `package`.

**Three registered sub-graphs are never handed off to.** `genesis`, `dream` and `fix`
are packages here because each is a standalone machine, and none is sequenced by the
main loop: `genesis` produces the preconditions the main loop *assumes*, `dream` runs
after the work like sleep so that reflection never gates a story, and `fix` is a
standalone drain of the backlog the main loop also drains inline, on its own copy of the
same nodes. All three are registered flows on the coder `Registry` and entered directly,
as `workhorse-coder run genesis`.

The other five are reached with `self.handoff(...)`, and the caller names the class at the
callsite::

    result = self.handoff(FixCi, branch=epic, docs_path=self.docs_path)

Two things follow from `Engine.handoff` that a sub-flow author has to know, because
neither is obvious from the callsite:

* only the run **writer** is subscoped, not the environment. A sub-flow's prompt paths
  therefore resolve against the *parent* package directory, which is why a flow names its
  own prompts from `coder/` down — `dev/prompts/implement-plan.md`, not
  `prompts/implement-plan.md`;
* `self.output(node)` reads that subscope, so it cannot see a node the parent ran and the
  parent cannot see one a sub-flow ran. A value that has to cross the boundary crosses it
  as an argument or as the `Done` value.

Each sub-flow gets its own transition budget, because `handoff` drives it through a fresh
`drive()` — a per-repo loop inside one cannot exhaust the parent's.

The YAML's name is `epic-coder`; the entry point and the console script are both
`coder`, matching the directory the library resolves it by today.
"""
