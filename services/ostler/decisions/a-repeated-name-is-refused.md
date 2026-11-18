story: SM-01M7AXZX1R8B9QKTKS7JMQGA5H
date: 2026-11-18
elements: TodoReorder

`ostler todo reorder` refuses a list that names the same queued epic more than once. The refusal prints
`epic '<epic>' named more than once` on standard output, exits 1 and writes no file. `<epic>` is the queue entry,
the epic's id, as `todo add` names the epic it finds already queued. It lives in `ostler/ostler/todo.py::reorder`,
which the command line and `Ostler.todo_reorder` share, so both refuse alike.

Two names stand for the same epic when they resolve to the same queue entry, the full name and the short handle
among them. `second`, the old name `0002-second` and the second epic's id are a repeat.

The unknown-name refusal runs first and keeps its own message, `not in queue: <names>`. A list that names an epic the
queue lacks, twice or not, is refused for that reason.

A repeated name is refused and not dropped silently. The queue holds an epic once, and `todo add` already refuses a
second copy. A repeat is most often a typo for another epic, so dropping it would reorder the queue on a guess and
tell the operator it worked. A refusal names the repeated epic and lets them type the list they meant. This overturns
the earlier behaviour recorded as entry 1 of `DISAGREEMENTS.md`, which wrote the epic into the queue twice.

The book plays the refusal with the same name twice, with a slug and its old name, with an old name and its slug, with
an id and its slug, with an epic the queue lacks twice and with an epic that is queued in some scenes and not in others. The book names two
positions, so a repeat further down a longer list is checked by the story's QA.

A queue file that already holds a repeat is not repaired.
