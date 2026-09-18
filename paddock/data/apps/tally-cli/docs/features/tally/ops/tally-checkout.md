---
type: environment
slug: tally-checkout
title: The checkout itself
---
# The checkout itself

- selector: the working copy, and there is no other. `tally` is stdlib only, so the interpreter
  on the machine and the files on disk are the whole of it.
- backing:
  - state: one JSON file per invocation, named by `--file`. Nothing is shared between two runs
    that do not name the same path, and nothing outlives the directory it was written into.
  - process: none. There is no port to bind, no container to start and nothing to wait for.
- local-only: true

The reason this node exists at all is that a runbook has to say where its steps run, and "here"
is an answer a book can be wrong about. Two things have to hold before `python3 -m tally` means
anything: the checkout is the current directory, and the interpreter is one the package's
`requires-python` admits. Neither is observable from the command's output once it has run —
a `tally` invoked against the wrong interpreter fails on syntax, which reads as a broken product.

Nothing is installed. `pyproject.toml` is present so the workspace's service marker resolves and
so `python -m tally` has a package to be part of; there is no build step, and a machine that has
run `uv sync` and a machine that has not both run the same code.
