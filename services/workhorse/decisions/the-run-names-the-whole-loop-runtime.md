story: none
date: 2026-11-17
elements: Run, Dot, Control, Replay

The sandbox plays `run` with `--dry-run` only, which walks the flow with a stand-in for every node. The command still reaches the whole loop runtime when a live backend drives it: the agent runner and its backends, the worktree cuts, the gate parking, the worklist and the telemetry. The `source` of `Run` names every module of the package except the ones below, so a change to the runtime is a reason to replay the command, even where the dry run only imports the module.

`Dot` also names the graph reader it draws from, `Control` names the listener side that a live run serves (workhorse/workhorse/control.py, workhorse/workhorse/reload.py) next to the offline rewind, and `Replay` names the turn record it re-reads.

Four things are left out of every element. The package `__init__` files that only re-export, the READMEs and the vendored copy of the shared core hold no behaviour a command reaches. `workhorse/workhorse/testing.py` is a set of helpers for the tests of a workflow author, and no command calls it.
