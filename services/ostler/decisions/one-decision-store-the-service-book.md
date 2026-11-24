---
story: none
date: 2026-11-24
elements: SearchPlan, LayoutApply
sources: ostler/ostler/layout.py::decision_moves, ostler/ostler/layout.py::check, ostler/ostler/model.py::doc_roots
---

A decision lives in one place, the `decisions/` folder of a service book, or a page of the product book. Ostler has no `decisions add` command and no `decisions` document root, so search reads the current book alone.

A repository or artifacts folder that still holds `docs/decisions/<slug>/decision.md` with a `repo:` key is refused. The refusal prints the commands that move each file to `products/<repo>/<slug>.md`. A taken target gets the suffix `-2`, then `-3`. A file in a code repository also gets `git rm -r --cached docs/decisions`.

Each moved page needs `date:` and `status:` lines in place of its frontmatter. A page that explains one element of one service moves to that service's `decisions/` folder. A file with no `repo:` key is not refused.
