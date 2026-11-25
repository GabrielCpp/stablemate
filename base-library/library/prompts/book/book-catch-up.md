---
description: "Bring stale service books back in step with their code: update changed elements, name new files, fix dead pointers, settle format findings, then play what changed. Run after code lands without its book delta."
argument-hint: "<repo root> [service module ...]"
---

# Catch up the books for $ARGUMENTS

Code landed and its books did not follow. This session brings each book back to the code
as it stands. The code is the authority for what a stale element says. The book's
decisions stay the authority for why.

Load {{ skill_link("ostler-book") }} before the first edit under a book.

## 1. Sort the books

For each book in the repo, or each module the arguments name, run:

```bash
ostler book stale <module> --app <repo root>
ostler book check <module> --app <repo root>
```

A book whose stale report is empty and whose check exits 0 needs nothing. Work the rest
one book at a time, the most stale first.

**Done when** each book is marked current or queued.

## 2. Update a stale book

Read the stale report. For each heading:

- **Changed files no element names** and **Changed functions no element names**: update
  the element the change belongs to, or add an element for the file. Ignore a file only
  when no served request runs it.
- **Pointers to files that no longer exist**: point the element at the file that now
  holds the code, or drop the element when its behaviour is gone.

Update changed elements in place to state the current behaviour.

**Done when** `ostler book stale` prints nothing under those three headings.

## 3. Settle format findings

Take the check's format findings and notes in batches of 15. Settle each one in the
batch, and only those. State it from the code, or decline it with one line in
`DECLINED.md`:

```markdown
- <Element>: <reason>
- <kind>: <reason>
```

A screen is `first` only when users land on it. A note stays open until the code settles
it.

**Done when** `ostler book check <module> --app <repo root>` exits 0.

## 4. Play what changed

Bring the stack up with `ostler env up`. List what the catch-up touched with
`ostler book affected <module> --app <repo root> --since HEAD`. Play each changed or added
call with `ostler book run <module> --only <call>`, one at a time. Fix a red play at its
cause. A wrong app goes in `DISAGREEMENTS.md` and the book keeps its intent.

**Done when** every changed and added call plays green or carries a line in
`DISAGREEMENTS.md`.

## 5. Verify and commit

Run `ostler book verified <module> --app <repo root>`. Commit each book by path with a
`docs` subject that names the service, such as `docs(api-service): catch the book up with
the code`.

**Done when** `ostler book verified` passes and each caught-up book has its commit. Then
start step 2 on the next queued book.
