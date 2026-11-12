story: workhorse-book
date: 2026-11-12
elements: Run

`workhorse-loop-runner ARGS` with no subcommand is `run ARGS` (workhorse/workhorse/cli/__init__.py, `_DEFAULT_COMMAND`). The book always spells `run` out, so the bare form is not a second command. An argparse usage error (exit 2) is reachable only through a flag combination the book does not build on purpose, and is not played.
