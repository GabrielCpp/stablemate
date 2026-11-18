story: none
date: 2026-11-18
elements: TodoAdd, TodoPrune, TodoReorder, TodoList, PathEpic, PathBranch, SeedAdd, SeedRemove, CreateStory, DeleteEpic, DeleteCreatedEpic, Unblock
sources: 136ae7630, ostler/ostler/model.py::Graph.epic_by_ref, ostler/ostler/path.py::epic_dir_under, ostler/ostler/todo.py::_queued_as

An epic's folder on the shelf is named by the epic's id, `art/epics/<id>/epic.md`, and its epic.md records the slug in
its frontmatter. A story's folder is named by the story's id, `stories/<id>/story.md`. A folder named `NNNN-slug` went
stale whenever an epic was renumbered or renamed, and every queue entry and milestone line that copied the name broke
with it. An id never changes, so a path built from it never goes stale.

Every command that names an epic takes its id, its slug, or an old `NNNN-slug` name. A name resolves by id, then by
folder, then by slug, and an old `NNNN-slug` name stands for the epic with its slug: `0002-second` names the second
epic. `path epic` prints the id folder. A name no epic has stays as typed: `path epic nope` prints `art/epics/nope`,
and `todo add 0009-nope` queues `0009-nope` with a warning that epic selection will skip it. `path branch --epic`
prints `feat/` and the slug of the epic the name stands for.

The queue keeps ids. `todo add third` queues the third epic's id and prints it, `todo list` prints ids, and the queue
file lists `[<id>](<id>/epic.md) — <title>`. `todo prune` and `todo reorder` match a name to the entry spelled as typed,
else to the first entry that stands for the same epic. A name no epic has matches only an entry spelled the same, so
`nope` does not match a queued `0009-nope`.

A refusal is a template over the request, so the fixtures carry `canonical`: the id of the sandbox epic a name stands
for, which is the queue entry a refusal names.
