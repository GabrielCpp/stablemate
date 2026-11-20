story: none
date: 2026-11-19
elements: NextEpic, DeleteEpic
sources: ostler/ostler/select.py::milestone_epics, ostler/ostler/select.py::next_epic, ostler/ostler/crud.py::delete_epic

The milestones are the one list of the work. ostler keeps no epics queue: no `ostler todo` command, no `index.md` queue
file on the epics shelf and no `epics-todo.json`. A repository that still holds either file keeps it as an ordinary file
that ostler never reads.

`Ostler.milestone_epics` gives every epic a milestone lists, once. A milestone's `dependsOn` milestones come first, and
each milestone gives its epics in the order its `epics:` list holds them. A superseded milestone gives no epics.
`next-epic` prints the first of them with unfinished work.

A shared queue let one run's progress change what every other run and every person saw. The coder worked the front of
the queue and committed each finished epic's removal, so two runs on one repository raced over one file. A run now keeps
what it finished on its own worklist, and the milestones change only when a person edits them.
