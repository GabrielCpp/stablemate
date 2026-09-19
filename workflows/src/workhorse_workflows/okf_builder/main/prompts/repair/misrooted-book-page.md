### `misrooted-book-page` — a typed page sits inside the wrong doc root

This file declares a real `type:` in frontmatter and sits under *a* doc root — so
`misplaced-book-page` never fires — but not under the root that type is registered for. Each
built-in type has exactly one home: `epic`/`story` → `docs/epics`, `milestone` →
`docs/milestones`, `feature` and every UI-profile type (`screen`/`concept`/`flow`/…) →
`docs/features`, `spec.*` → `docs/specs` (or a paddock app's own equivalent, per `ostler.yml`'s
`docRoots`). The finding's message names both: the type's registered root, and the root the
file was actually found under.

The most common concrete shape: `ostler qa context` stamps its scratch output
`type: spec.qa-okf-context` and writes it under the specs directory. When a copy, a stray
`git mv`, or a hand-authored draft ends up under `docs/features` instead, its file-level node
is quietly suppressed (`spec` is not a UI type) but its `##` sections are still parsed and
seeded into the book as `untyped` nodes — content nobody meant to be part of the book, sitting
inside it with no diagnostic until this check existed.

1. **Move the file to the doc root its `type:` actually belongs to.** For a `spec.*`-typed
   file this means `docs/specs/`; for any other type, the doc root the finding names. Re-run
   `ostler fmt` at the new path so frontmatter and heading shape stay conformant, and fix
   anything that linked to the old path (`ostler doctor` lists the resulting `dangling-link`s).
2. **When the file is scratch output that was never meant to be read at all** — a stray
   `qa context` run, a copy left behind by a scaffold mistake — **delete it** rather than
   relocating it. Confirm nothing links into it first; if something does, that link is a
   separate finding for whoever owns the referring page, not a reason to keep this file.

**Never repair this by changing the file's `type:` to match the root it happens to sit in.**
That erases the fact the file was misfiled instead of fixing it — a `spec.qa-okf-context`
retyped to fit under `docs/features` is still scratch output, now permanently declared a book
page. The file belongs at the path its declared type names, not the other way around.
