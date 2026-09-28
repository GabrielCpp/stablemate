# cli

The command line a workflow's console script binds. Each subcommand is one module with a `NAME`, a `HELP`, its arguments and its `run`.

## Map

- `control.py`: the `control` subcommand that steers, questions, answers or stops a live run.
- `dot.py`: the `dot` subcommand that prints the workflow's state machine as Graphviz DOT.
- `inbox.py`: the `inbox` subcommand that reads and replies to operator messages.
- `offline.py`: the `control` verbs that act on a run no process serves: `rewind`, `resume` and the checkpoint's params.
- `params.py`: merging `--params` and `--params-file` into the map a workflow is built from.
- `parser.py`: the table of subcommands and the one parser built from it.
- `replay.py`: the `replay` subcommand that reruns one recorded agent turn from the tree it started on.
- `run.py`: the `run` subcommand's arguments, and which backend, profile and config a run uses.
- `target.py`: which run directory an operator command means, by name or through groom's live list.
- `version.py`: the `version` subcommand that prints the installed engine version.
