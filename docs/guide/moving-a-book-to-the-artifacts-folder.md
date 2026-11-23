# Moving a book to the artifacts folder

A book lives in the artifacts folder unless the repository's `agents.yml` sets `book: {home: repo}`. A repository that still holds an ostler book without that key is refused by every `ostler book` command. This page moves the book out of the repository. To keep the book in the repository instead, add `book:\n  home: repo` to its `agents.yml` and stop here.

The move is a change with no story. It commits on the artifacts base and on the repository's base, never on a book branch.

Run every command from the repository root. `<artifacts>` is the artifacts folder, the one `$STABLEMATE_ARTIFACTS_DIR` or the `artifacts_dir` of `config.toml` names. `<product>` is explained in step 4.

## Steps

1. Land or rebase every branch and worktree of the repository that still edits `services/` or `product/`. The move deletes those folders on the base, and a branch that edits them afterwards conflicts.

   ```bash
   git worktree list
   git branch --no-merged
   ```

2. Check the artifacts repository is clean and on its base branch.

   ```bash
   git -C <artifacts> status --porcelain
   git -C <artifacts> branch --show-current
   ```

   The first command prints nothing. The second prints the base branch. If the artifacts folder is not a git repository yet, run `git -C <artifacts> init` and make a first commit.

3. Move `services/` into the repository's folder of the artifacts folder. The folder is `<artifacts>/services/<repo>/`. `<repo>` is the repository's name: the workspace member name, or the folder name in lower case with `.` and `_` written as `-`. A repository folder `Acme_App` is `acme-app`. Add `--repo <repo>` to name it yourself. The name holds no `.` and no `/`.

   Run the move with `--dry-run` first. It prints each `would move` and `would rewrite` line and changes nothing. Read every `check by hand` line it prints.

   ```bash
   ostler book move --from services --dry-run
   ostler book move --from services
   ```

   With `--from` and no names, the move takes every entry of `services/`, which includes the shared stack root `services/ops/`. That folder moves with the books and becomes `services/<repo>/ops/`.

   The move stops with exit 2, and changes nothing, in three cases. A name has no folder under `services/`. `services/<repo>/` already holds a folder of that name. A book imports a moved book with an absolute `from services.<name>` or `import services.<name>` line while `<repo>` is not a Python identifier, such as `acme-app`. Write that import as a relative import first, because no import statement can spell `services.acme-app.<name>`.

   The move rewrites every `services.<name>` module name in `.py`, `.md`, `.tsv`, `.yml`, `.yaml`, `.j2` and `.toml` files under `<artifacts>/services/`. It deletes a leftover `index.tsv` of a moved book, because search keeps its index in the user cache. It leaves slash paths alone and lists each line that holds a `services/<name>/` path as `check by hand: <path>:<line>: <text>`. Step 5 covers those lines. It deletes the bytecode caches of the moved folders.

4. Copy the product pages, `product/*.md`, to `<artifacts>/products/<product>/`. The product is `book.product` in the repository's `agents.yml`. Without that key it is the repository folder's name in lower case, with `.` and `_` written as `-`. A repository folder `Acme_App` has the product `acme-app`.

   ```bash
   mkdir -p <artifacts>/products/<product>
   cp product/*.md <artifacts>/products/<product>/
   ```

   Skip this step when the repository has no `product/` folder. Once the move is done, `ostler book search <a word of a page>` run from the repository prints `== product <product>` above the page, and that heading is the check.

5. Rewrite the pointers that the move leaves wrong. Start with the `check by hand` lines of step 3.

   - A module name of the repository's own books is rewritten by the move, as in `services.<repo>.<name>`. A book of another repository is `services.<other>.<name>`.
   - A bare `source=` pointer such as `app.py::handler`, and a `sources:` line of a decision, stay as they are. They resolve against `--app`, the code checkout, so `ostler book check services.<name> --app .` still finds the file.
   - A stack `Fresh` `cwd`, an `ops/` `cwd` and a relative path in a stack command now resolve under the book root, which is the artifacts folder. Write the code checkout out as `repo://<name>/<path>`, where `<name>` is the repository's name. `cwd="ops"` becomes `cwd="repo://acme/ops"`.
   - `{{ repo }}` in a compose template is the book root. Write `{{ repos['<name>'] }}` for the code checkout.
   - A stack fixture that names a file of the code repository is written `repo://<repo>/<path>`. A path such as `../../../db/seed.sql`, which climbed out of the book into the repository, no longer resolves. A fixture path with no scheme still resolves beside the stack file.
   - An `Environment` whose `root=` is derived from the book's own path, such as `Path(__file__).resolve().parents[2]`, now names the artifacts folder. Remove the `root=` and the constant that fed it. The environment then reads the stack copy of the code checkout the command runs in.

6. Delete `book: {home: repo}` from the repository's `agents.yml` if it is there. Delete the `book:` table when `home` is its only key.

7. Commit the artifacts side first, on the artifacts base.

   ```bash
   git -C <artifacts> add services products
   git -C <artifacts> commit -m "docs(book): move the <repo> book from its repository"
   ```

8. Commit the repository side, on the repository's base.

   ```bash
   git rm -r services product
   git add agents.yml
   git commit -m "docs: move the book to the artifacts folder"
   ```

   Leave `agents.yml` out of `git add` when step 6 changed nothing. The move already took the files out of `services/`. If the `git rm` pathspec matches nothing in the index, use `git add -A services` in its place.

9. Check the move from the repository.

   ```bash
   ostler book check services.<repo>.<name> --app .
   ostler book pages
   ```

   Both exit 0. A `source=` pointer that is not found names the file, so a missed rewrite from step 5 shows here.

## A flat book already in the artifacts folder

A book that sits at `<artifacts>/services/<name>/`, with no repository folder, is a flat book. A search or a check started in its repository names it and prints the command that moves it. Move it as follows.

1. Check the artifacts repository is clean and on its base branch, as in step 2.

2. Run the move from `<artifacts>`. Name every book of that repository, and add `ops` and any shared package or file such as `__init__.py` that belongs to it. A flat surface-split book, `services/<name>/<surface>/`, moves the same way, under its `<name>`. Run `--dry-run` first.

   ```bash
   ostler book move <name> ... --repo <repo> --dry-run
   ostler book move <name> ... --repo <repo>
   ```

3. Read the `check by hand` lines and fix each one.

4. Commit the move on the artifacts base.

   ```bash
   git -C <artifacts> add -A services
   git -C <artifacts> commit -m "docs(book): move the <repo> books into their repository folder"
   ```

5. Check from the repository.

   ```bash
   ostler book check services.<repo>.<name> --app .
   ```

   It exits 0.

A flat book that sits on an open book branch moves in that branch's worktree. Move the artifacts base first, then rebase the branch onto it or rebuild the branch. Start the command in the worktree, with `--repo <repo>`, or run it from anywhere with `--to <worktree>` and `--repo <repo>`. The move writes into the checkout it is started in, or into the one `--to` names, and writes nothing to the artifacts base then.

## Afterwards

A branch of the repository gets its own book branch with `ostler book branch`, which prints the book root of that branch. `ostler book land` lands it on the artifacts base by rebase, with no merge commit, and removes the worktree and the branch.
