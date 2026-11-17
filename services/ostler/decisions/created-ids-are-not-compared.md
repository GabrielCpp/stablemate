story: none
date: 2026-11-17
elements: CreateEpic, CreateStory

`ostler create epic` and `ostler create story` mint an id and print it on the line that says what was created
(`created epic '0004-fourth' (TST-...)`). The id is a fresh ULID in every world, so the book cannot say it. The
commands declare that line opaque and the model says nothing for them. What the commands did is judged by the watch:
the new `epic.md` or `story.md` appears in the listing, and the epic's page gains the story's heading and title.

A story the book creates has an id no later step can name, so the book never sets its status, deletes it or updates it.
Those commands play on the three stories the sandbox starts with.

A bare slug takes the number after the highest epic folder: `fourth` becomes `0004-fourth` in the seeded plan. A name
that already carries a number is used as typed, and the new epic is not queued. `create story` into a slug the epic
already holds changes nothing and answers success with `story '<slug>' already exists in epic '<epic>'`.

The refusal for an epic that exists names the folder, so `create epic second` is refused as `epic '0002-second'
already exists`. The model can name that folder only for the epics the sandbox starts with, so the cells never create
an epic twice.
