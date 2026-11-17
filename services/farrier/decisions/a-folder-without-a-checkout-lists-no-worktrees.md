story: none
date: 2026-11-16
elements: Worktrees, Workflows, WorkflowNames

`farrier worktrees` walks the checkouts under the folders it is given and under the configured `worktree_dir`
(`farrier/farrier/worktree_sweep.py`). The sandbox holds no git checkout, so the listing is empty and the command
exits 0 without the "Nothing changed" line. `farrier workflows` reads the pipx environments of the machine; the
sandbox's home is a folder of its own, so no distribution is installed and the command says so. `--names` prints one
empty line in that case. A machine with workflows installed lists them, which the book does not state.
