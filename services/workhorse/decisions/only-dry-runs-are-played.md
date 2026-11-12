story: workhorse-book
date: 2026-11-12
elements: Run

The book plays `run` only with `--dry-run`, which is written into the argv as a word. A run without it drives a live agent backend (workhorse/workhorse/cli/run.py::run), which the sandbox does not provide and which would make the answer depend on the machine. The dry run walks the loop with a stand-in for every node, so the files it writes and the lines it prints are the same in every world. The refusals of `run` (an unknown backend, profile, workspace, config, params or context file) are played because the runner checks them before it starts anything.
