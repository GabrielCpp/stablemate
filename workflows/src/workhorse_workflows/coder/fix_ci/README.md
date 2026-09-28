# fix_ci

The CI fix lane of the coder workflow. It walks the workspace and gets each epic branch green.

## Map

- `flow.py`: the `FixCi` state machine. It polls a PR's Actions runs, hands a failure to a fixer, pushes and polls again.
