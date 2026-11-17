# Where the markdown pages and farrier disagree

Found while writing this book from the markdown pages it replaced. Each entry names the page, the claim, and what the
tool does.

1. `farrier-commands-init.md`, the `config` command, args: `set-library <path>` is said to error "unless `path`
   contains both a `library/` and a `packs/` directory". `is_library_dir`
   (`farrier/farrier/_vendor/stablemate_core/layout.py:8-10`) tests `library/` alone, and `farrier config
   set-library lib` accepted a directory that holds `library/` and no `packs/`. The page
   `concepts/library-directory.md` line 36 says the same as the tool, so the pages also disagree with each other.

2. `farrier-commands-install.md`, flags: `--library <dir>` is "the library directory (the `agents/` tree)". The
   tool refuses a directory that has no `library/` folder with "must contain library/"
   (`farrier/farrier/layers.py:124-127`) and does not look for `agents/`. `farrier install --help` carries the same
   `agents/` wording.

3. `farrier-commands-install.md`, the `does` list: nothing says install writes `.githooks/pre-commit` and
   `.agents/hooks/pre-commit` in a repository with no hook manager, or that it prints "Wired `make
   farrier-run-hook` into .githooks/pre-commit" there. `farrier-commands-workflows.md` shows that line only for
   husky. The tool wires the `githooks` manager when nothing else is detected
   (`concepts/hook-manager-wiring.md` line 117), so the install page's list of files install renders is incomplete.

4. `farrier sync`, in a directory that is not a git checkout: with an `agents.yml` and a library the home config
   resolves, `_run_sync` (`farrier/farrier/cli.py:1065`) reaches `dirty_paths` (`farrier/farrier/sync.py:38`), whose
   `git status` exits 128 and the `CalledProcessError` ends the command in a traceback with exit 1. Without a
   resolvable library the same command skips the check and exits 0, so the command is graceful in one case and
   crashes in the other. The command is a commit check, which only runs inside a checkout, so the book plays it
   before the sandbox has a library and never after.
