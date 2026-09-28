# loop_runner

The `loop-runner` workflow. It hands one plan to one agent turn and lets the agent's own tool loop carry it out.

## Map

- `workflow.py`: the single-state `LoopRunner` flow, its reply shape, and the `loop-runner` command.
