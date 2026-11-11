# Where the markdown pages and farrier disagree

Found while writing this book from `docs/services/farrier/`. Each entry names the page, the claim, and what the
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
