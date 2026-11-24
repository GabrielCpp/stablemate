---
story: none
date: 2026-11-24
elements: CreateMilestone, MilestoneEpicsFirst, MilestoneEpicsBoth, MilestoneEpicsUnknown, MilestoneSourceItem, PathNotes, PathDesign, PathMilestone
sources: ostler/ostler/model.py::doc_roots, ostler/ostler/layout.py::check, core/stablemate_core/books.py::product_home
---

Milestones live in the artifacts folder at `products/<product>/milestones/NNNN-<slug>/milestone.md`. Design notes live at `products/<product>/designs/<slug>.md`. Before, a milestone sat in the `docs/milestones/` of the repository.

The resolver takes the code checkout, not the root. `find_root` turns a workspace member into the artifacts folder, so the folder the user stands in no longer names the repository. `doc_roots`, `load` and `Ostler` receive that checkout as `start`, and `books.product_home` reads the product from it. `find_root` is kept as it is.

The folder nests under `products/<product>/`, and `book pages --level product` reads only the top-level pages of that folder. A test holds the guard: a milestone folder never shows up as a page.

Numbers are per product. The first milestone of each product is `0001`, and the next one is one past the highest in that product's folder.

`create milestone` refuses when no product resolves, which is the case from the artifacts folder. The message says to run it from the code repository, with `ostler -C <repo>`.

A repository that still holds `docs/milestones/*/milestone.md` is refused with the commands that move it, as for decisions: `mkdir -p`, `mv` and `git rm -r --cached`. The same holds for `docs/milestones/` in the artifacts folder, which moves with `git mv`. A number already taken in the product folder moves to the next free one.

`ostler path notes <slug>` and `ostler path design <slug>` print a place and create nothing. `ostler path milestone <slug>` prints the folder of a milestone that exists and refuses otherwise.

A linked worktree is judged by its main checkout. A run's worktree is cut from a commit that may still hold the old folders, so the refusal reads the main checkout and names it in the commands it prints.
