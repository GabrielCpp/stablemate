story: none
date: 2026-11-19
elements: DryRunCoder
sources: workflows/src/workhorse_workflows/coder/shared/queue.py::resolve_launch, workflows/src/workhorse_workflows/author/finalize/nodes/artifacts.py::validate_artifacts

A coder launch over every epic, `epic=all` and the default, files the open stories of every epic the project's
milestones list. The epics come in milestone order: a milestone's `dependsOn` milestones first, then its `epics:` list
in order. A superseded milestone gives none. The run files those stories on its own worklist and tracks what it
finished there. It never writes the milestones.

There is no shared epics queue. The coder reads no `index.md` on the epics shelf and no `epics-todo.json`, and keeps no
fallback for either. A run used to remove each finished epic from the shared queue and commit that change, so one run's
progress changed what the next run and every person saw. A person now decides what gets worked by editing the
milestones.

A launch over every epic fails before any turn when no milestone lists an epic, or when a milestone lists an epic the
book does not hold. Author's last check judges what it wrote against the same list, so an Author run that ends green
leaves the coder something to run.
