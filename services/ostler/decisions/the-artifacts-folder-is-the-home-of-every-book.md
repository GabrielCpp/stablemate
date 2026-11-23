story: none
date: 2026-11-22
elements: SearchBook, CheckBook, SearchUnmovedBook, MoveBook, EnvCheck
sources: core/stablemate_core/books.py::book_home, ostler/ostler/book/index.py::book_root, core/stablemate_core/book_branch.py, ostler/ostler/book/home.py, ostler/ostler/book/move.py, core/stablemate_core/books.py::service_package, ostler/ostler/book/index.py::services_of, ostler/ostler/environments/spec.py::stack_roots, ostler/ostler/environments/spec.py::_read_secrets, ostler/ostler/environments/leases.py::books_near, ostler/ostler/environments/runtime.py::copy_owner, ostler/ostler/environments/runtime.py::copy_for, ostler/ostler/environments/runtime.py::copies, ostler/ostler/milestones.py::_book_homes

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

A book change is committed in the artifacts repository on a branch with the same name as the code branch of the same
work. For a story that is the story's branch. A book branch always lives in a linked worktree of the artifacts
repository, and the artifacts folder itself never leaves its base branch, so two pieces of work in two repositories
never switch one shared checkout. The book branch lands on the artifacts base when the code lands on its base, by
rebase and fast-forward, never a merge commit. A change with no code branch, committed straight on the code's base,
commits its book straight on the artifacts base. With `book.home: repo` there is no book branch: the book rides the
code's branch.

`ostler book branch` opens the book branch for the current code branch and prints the book root. `ostler book land`
lands it and removes the worktree and the branch. A conflict keeps both and names the files. The book does not play
`branch` and `land`, because the demo world is not a git checkout, as for `affected` (see
`a-storys-change-is-its-own-commits.md`).

The artifacts folder namespaces the books by repository: a book is `services/<repo>/<name>/`, and its module is
`services.<repo>.<name>`, or `services.<repo>.<name>.<surface>` for a book split by surface. `<repo>` is the repository's
name. Books of different repositories name each other by their full module, as in `owner="services.<other>.<name>"`.
`book search` without `--service` reads the books of the repository it is started in, and every book when started in the
artifacts folder or in a repository that keeps its book. A book at the old flat place, `services/<name>/` in the
artifacts folder, is skipped with a line on standard error that names the move, and the "no book" error of a command that
asks for it names the move too. Neither is a refusal, because a refusal would stop every repository that shares the
folder until all its books moved.

`ostler book move [NAME ...] [--repo REPO] [--from FOLDER] [--to FOLDER] [--dry-run]` moves each named flat book into
`services/<repo>/` of the artifacts folder. With `--from` it moves the entries of that folder, such as a repository's own
`services/`, and with `--to` it writes to that folder instead of the artifacts folder. It prints `moved <path> to <path>`
for each entry and `rewrote <n> reference(s) in <path>` for each file it changed, and with `--dry-run` it prints `would
move` and `would rewrite` and changes nothing. It rewrites module names, `services.<name>` to `services.<repo>.<name>`,
in the `.py`, `.md`, `.tsv` and configuration files under `services/`. It never rewrites a slash path such as
`services/<name>/handler.py` in a `source=` pointer. It lists each such line as `check by hand`. It refuses, and changes
nothing, when a target exists, when a source is missing, or when a book holds an absolute import of a moved module and the
repository's name is not a Python identifier.

A repository name that is not a Python identifier, such as `acme-app`, cannot appear in an `import` statement. A book
imports its own modules relatively, and `book move` refuses an absolute import into such a name. The loader reaches the
book through `importlib`, which loads `services.acme-app.api` without trouble.

Each repository folder in the artifacts folder is a stack root, `services/<repo>/ops/stack.yml`, and the stacked books
below it keep their folder names. One `secrets:` source is allowed across all the stack roots, and a second one is an
error. A stack fixture is a path beside the book's `ops/` folder, or `repo://<name>/<path>` into the code repository.
A `secrets:` file takes the same `repo://<name>/<path>` pointer, and in a linked worktree that lacks the ignored file, the file of the repository's main checkout is read, as for a relative path.
A command started for a code repository loads the stack roots of the repositories it knows, which are the repository
itself or the members of its workspace. Two unrelated products in one artifacts folder never see each other's stacks.
Started in the artifacts folder, or in a checkout of the artifacts repository, every stack root loads, and two
same-named books are refused there with the error of a duplicate book.

A stack copy is named after the code repository, so two products in one artifacts folder never share a copy. A command
started for a code repository outside the artifacts folder names its copies `<repo>-<copy>`, or `<workspace>-<copy>` when
the repository runs in a workspace. A command started in the artifacts folder names them after the folder, as before,
and a book root that is not the artifacts folder keeps naming them after its own repository. `env up`, `down`, `exec`,
`reset`, `address`, `compose`, the leases and the QA runner all take the code checkout, so a copy is torn down under the
name it came up under, and `env ls` lists the copies of the product it is started for.

A milestone's books are read from the repositories the command knows. A story that names the service `api` is matched with
the `api` book of its own repository, or of the members of its workspace, and never with another product's `api`. Started
in the artifacts folder, every repository folder is read.

The sandbox keeps its book in the repository, so it is not a namespaced root. The book plays `MoveBook` against `art/`,
the sandbox's artifacts folder, where `ostler -C art book move flat --repo acme` moves a flat book into `services/acme/`.
It does not play `--from` or `--dry-run`, because the sandbox holds no second folder to move from.
