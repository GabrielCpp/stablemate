---
description: "Write a service's first book from its code: every endpoint, screen and command as an element, the reasons behind each screen, then laps of check, play and missing until the book covers the app."
argument-hint: "<repo root> [service name]"
---

# Write the first book for $ARGUMENTS

The book states what the app does today, read from its code, docs and history. It
replays against the running app, so every claim is one a play can confirm. Write in
passes: breadth first, reasons second, then laps until the checks pass.

Load {{ skill_link("ostler-book") }} before the first file. It says where the book lives,
its format and the bar each element meets.

## 1. Read the app

List every surface the app serves: HTTP, gRPC, CLI, web screens and mobile screens. Find
each entry point, route table and screen registry. Read the app's README and its docs
folder.

**Done when** you can name each surface and the files that declare its entries.

## 2. Breadth pass

Lay out the book. A book with more than one surface keeps a shared `model/` and one
`<surface>/service.py` per surface. Then write one element per entry:

- An endpoint or command element per route, with its refusals and its `source=` pointer.
- A `Screen` class per screen, with its route, its name, `first` when users land on it,
  its source and its components with the text in every language the app ships. A dialog
  or tab carries `inside` and `shown_in`. Text you cannot find in every language goes in
  `left`.

Work through the entries in batches of about eight files, and run
`ostler book check <module> --app <repo root>` after each batch.

**Done when** `ostler book missing <module> --app <repo root>` lists no file that serves a
request. Each remaining file is named by an element's `source` or matched by an
`App(ignore=...)` pattern.

## 3. Reasons pass

For each screen and each rule, find why it is so in `git log`, the docs and the code's
own text. Write each reason as a decision file under `decisions/` with `story:` and
`sources:` fields. A reason no source gives becomes one line in `QUESTIONS.md`:

```markdown
- <Screen>: <question>
```

Where the app contradicts its own docs, write the contradiction in `DISAGREEMENTS.md`. A
cell of the behaviour no source settles goes in `UNDERSPECIFIED.md`.

**Done when** every screen has a decision file or a line in `QUESTIONS.md`.

## 4. Laps

Bring the stack up with `ostler env up`. Then repeat:

1. `ostler book check <module> --app <repo root>`
2. `ostler book run <module> --only <call>` for each call you touched since the last lap.
   Run one play at a time, in the background, and wait on its exit.
3. `ostler book missing <module> --app <repo root>`

Fix each finding at its cause. A play that fails because the app is wrong goes in
`DISAGREEMENTS.md`, and the book keeps the behaviour the docs promise. Stop after three
laps that leave the same finding and report it with its output.

**Done when** check and missing exit 0 and every touched call has passed one `--only`
play.

## 5. Verify and commit

Run `ostler book verified <module> --app <repo root>`. Read the book's format rules in the
ostler-book skill once more and fix each element that breaks them. Commit the book by path
with a `docs` subject.

**Done when** `ostler book verified` passes and the commit holds only files under the
book.
