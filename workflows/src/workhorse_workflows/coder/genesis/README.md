# genesis

The genesis lane of the coder workflow. It takes a directory and leaves a repo the main loop will accept.

## Map

- `flow.py`: the `Genesis` state machine. It owns the order of the genesis steps.
- `nodes.py`: what each genesis step does to the target, and the check that the result meets the main loop's preconditions.
