---
story: none
date: 2026-11-24
elements: FileDecision
sources: ostler/ostler/model.py::doc_roots, ostler/ostler/layout.py::check
---

Decisions and ADRs of every repository live in the artifacts folder under `docs/decisions/<slug>/` and `docs/adrs/<slug>/`, whether or not a workspace lists the repository. Before, a repository in no workspace kept them under its own `docs/`.

Only `doc_roots` changed. `find_root` is kept, because the root also locates the manifest, the templates and the run folders.

Milestones stay in the repository, because the operator reviews them there.

A repository that still holds a `docs/decisions/*/decision.md` with a `repo:` key or a `docs/adrs/*/adr.md` is refused with the commands that move it: `mkdir -p`, `mv` and `git rm -r --cached`. Reading both places would split where a decision is filed from where it is read. A taken slug moves to `<slug>-<repo>`. A file with no such shape is not refused.

Repositories that share the folder stay apart by global slugs and by the `repo:` key of each decision. A slug filed by one repository is refused for the next.
