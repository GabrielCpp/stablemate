### `misplaced-book-page` — a typed page sits outside every doc root

This file declares a real `type:` in frontmatter, but it is not under any of `graph.doc_roots`
(`docs/features`, `docs/epics`, `docs/milestones`, `docs/roadmaps`, `docs/specs`, `specs`, or a
paddock app's own `docs/<kind>`). Every book-facing check walks *in* from those roots, so this
page is not merely wrong — it is invisible: nothing validates it, nothing reaches it from
`ostler trace`, and a real referrer's link into it shows up elsewhere as `dangling-link` while
this file itself raises nothing on its own account until now.

Two different situations produce this, and they repair differently:

1. **The page belongs in the book and moved (or was authored) in the wrong place** — a `git mv`
   that landed one directory short of `docs/features/<service>/`, a scaffold run with the wrong
   `--service`, a hand-written file dropped beside the doc root instead of inside it. Move the
   file under the doc root its `type:` belongs to — a `screen`/`component`/`interaction`/… goes
   under `docs/features/<service>/…`, an `epic` under `docs/epics/`, and so on — then re-run
   `ostler fmt` on it so the frontmatter and heading shape are still conformant at the new path.
   Fix every link that pointed at the old path; `ostler doctor` will list them.
2. **The file was never meant to be a book page** — a draft, a note, a doc copied from
   elsewhere that happens to carry a `type:` key left over from a template. Remove the `type:`
   bullet (or the whole frontmatter block) so the file stops presenting itself as a Concept.

**Never leave the file where it is with `type:` intact.** Doing so keeps the exact defect this
finding exists to surface: a node claiming membership in the book that no check will ever read
again once this pass is done.
