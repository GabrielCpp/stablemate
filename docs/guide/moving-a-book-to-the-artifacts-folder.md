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

   The first command prints nothing. The second prints the base branch. If the artifacts folder is not a git repository yet, run `ostler book branch` once from any code repository, or `git -C <artifacts> init` and make a first commit.

3. Copy `services/` to `<artifacts>/services/`. Service ids are unique across the folder, so a folder that already exists there stops the move. Remove bytecode caches from the copy.

   ```bash
   ls services
   ls <artifacts>/services
   mkdir -p <artifacts>/services
   cp -r services/. <artifacts>/services/
   find <artifacts>/services -name __pycache__ -prune -exec rm -r {} +
   ```

4. Copy the product pages, `product/*.md`, to `<artifacts>/products/<product>/`. The product is `book.product` in the repository's `agents.yml`. Without that key it is the repository folder's name in lower case, with `.` and `_` written as `-`. A repository folder `Acme_App` has the product `acme-app`.

   ```bash
   mkdir -p <artifacts>/products/<product>
   cp product/*.md <artifacts>/products/<product>/
   ```

   Skip this step when the repository has no `product/` folder. Once the move is done, `ostler book search <a word of a page>` run from the repository prints `== product <product>` above the page, and that heading is the check.

5. Rewrite the pointers that the move leaves wrong.

   - A bare `source=` pointer such as `app.py::handler`, and a `sources:` line of a decision, stay as they are. They resolve against `--app`, the code checkout, so `ostler book check services.<name> --app .` still finds the file.
   - A stack `Fresh` `cwd`, an `ops/` `cwd` and a relative path in a stack command now resolve under the book root, which is the artifacts folder. Write the code checkout out as `repo://<name>/<path>`, where `<name>` is the repository's name. `cwd="ops"` becomes `cwd="repo://acme/ops"`.
   - `{{ repo }}` in a compose template is the book root. Write `{{ repos['<name>'] }}` for the code checkout.

6. Delete `book: {home: repo}` from the repository's `agents.yml` if it is there. Delete the `book:` table when `home` is its only key.

7. Commit the artifacts side first, on the artifacts base.

   ```bash
   git -C <artifacts> add services products
   git -C <artifacts> commit -m "docs(book): move the <name> book from its repository"
   ```

8. Commit the repository side, on the repository's base.

   ```bash
   git rm -r services product
   git add agents.yml
   git commit -m "docs: move the book to the artifacts folder"
   ```

   Leave `agents.yml` out of `git add` when step 6 changed nothing.

9. Check the move from the repository.

   ```bash
   ostler book check services.<name> --app .
   ostler book pages
   ```

   Both exit 0. A `source=` pointer that is not found names the file, so a missed rewrite from step 5 shows here.

## Afterwards

A branch of the repository gets its own book branch with `ostler book branch`, which prints the book root of that branch. `ostler book land` lands it on the artifacts base by rebase, with no merge commit, and removes the worktree and the branch.
