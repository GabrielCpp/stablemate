story: none
date: 2026-11-22
elements: SearchBook, CheckBook, SearchUnmovedBook
sources: core/stablemate_core/books.py::book_home, ostler/ostler/book/index.py::book_root

A book lives in the artifacts folder unless the repository says otherwise. `ostler book` resolves its book root through
one function of the shared core, `book_home`, and no command walks up from the working directory looking for a
`services/` folder.

A repository that sets `book: {home: repo}` in its `agents.yml` keeps its book beside its code. The nearest `agents.yml`
at or above the working directory decides, and the walk stops at the repository top, so a fixture folder with its own
`agents.yml` is its own book root. A repository with no key reads its book in the artifacts folder. A start inside the
artifacts folder, or inside a worktree of the artifacts repository, reads that checkout. A start in a worktree of the
code on a branch reads the artifacts worktree on the same branch when one exists, and the artifacts folder otherwise.

A repository that still holds an ostler book where the artifacts folder is now the home is refused. The refusal is a
`service.py` at `services/<name>/` or `services/<name>/<surface>/` whose text imports `ostler.book`, in a repository whose
`agents.yml` does not keep the book. The command exits 2 and names both ways out: set `book: {home: repo}`, or move the
book to the artifacts folder with the guide. A `services/` folder that holds no ostler book, such as an application's own
`services/user/service.py`, is not refused.

A source pointer written `repo://<name>/<path>` resolves for a lone repository, from the repository itself or from
`--app`. The name is the repository's name, as for a member of a workspace. A bare pointer resolves against `--app`.

Stablemate and the sandbox keep their book through `book.home: repo`. The sandbox also holds `unmoved/`, a repository
with an ostler book and no key, so the book plays the refusal.
