story: none
date: 2026-11-18
elements: CreateEpic, CreateStory, DeleteCreatedEpic
sources: 136ae7630, ostler/ostler/crud.py::create_epic, ostler/ostler/crud.py::create_story

`ostler create epic <slug>` mints an id, writes `art/epics/<id>/epic.md` with the id, the slug, the title and the
status `planned` in its frontmatter, and prints `created epic '<slug>' (<id>)`. `ostler create story` mints an id,
writes `stories/<id>/story.md` and prints `created story '<slug>' (<id>) in epic '<epic>'`. The id is a fresh ULID in
every world, so the book cannot say it, and the folder the command writes carries it.

The book therefore declares those lines opaque, and the watch reads only the folders the sandbox starts with, each by
its id. The model keeps a created epic as a `MintedEpic` by its slug and a created story as a `MintedStory` by its
epic and slug, so the commands that follow answer as the app does: a story filed under the new epic, a second story
with the same slug reported as already there, the new epic's slug refused to a second `create epic`. A story created
under one of the sandbox's epics is read from that epic's page, which gains the story's heading and title.

`create epic` takes a slug. An old `NNNN-slug` name gives the slug alone, so `create epic 0007-seventh` makes the epic
`seventh`. A slug an epic already has is refused with `epic '<slug>' already exists (<folder>)`, and the folder is an
id. The model can name that folder only for the epics the sandbox starts with, so no cell creates an epic twice.
`create story` into a slug the epic already holds changes nothing and answers success with
`story '<slug>' already exists in epic '<epic>'`, the epic as typed.

`delete epic` of a created epic prints `deleted epic '<id>'`. `DeleteCreatedEpic` plays that call with the line left
out, and the journey reads the deletion from the `create story` that follows, which the app refuses with
`no epic '<slug>'`. The sandbox's epics are deleted through `DeleteEpic`, whose line the book compares.

A story the book creates has an id no later step can name, so the book never sets its status, deletes it or updates it.
Those commands play on the three stories the sandbox starts with.
