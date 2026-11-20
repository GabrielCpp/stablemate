story: none
date: 2026-11-18
elements: PathEpic, PathBranch, SeedAdd, SeedRemove, CreateStory, DeleteEpic, DeleteCreatedEpic, Unblock
sources: 136ae7630, ostler/ostler/model.py::Graph.epic_by_ref, ostler/ostler/path.py::epic_dir_under

An epic's folder on the shelf is named by the epic's id, `art/epics/<id>/epic.md`, and its epic.md records the slug in
its frontmatter. A story's folder is named by the story's id, `stories/<id>/story.md`. A folder named `NNNN-slug` went
stale whenever an epic was renumbered or renamed, and every milestone line that copied the name broke
with it. An id never changes, so a path built from it never goes stale.

Every command that names an epic takes its id, its slug, or an old `NNNN-slug` name. A name resolves by id, then by
folder, then by slug, and an old `NNNN-slug` name stands for the epic with its slug: `0002-second` names the second
epic. `path epic` prints the id folder. A name no epic has stays as typed: `path epic nope` prints `art/epics/nope`.
`path branch --epic`
prints `feat/` and the slug of the epic the name stands for.

A refusal is a template over the request, so the fixtures carry `canonical`: the id of the sandbox epic a name stands
for, which is the folder a refusal names.
