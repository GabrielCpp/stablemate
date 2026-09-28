# docs

The docs lane of the coder workflow. It folds a finished story into the as-built OKF book and checks that claim against the diff.

## Map

- `flow.py`: the `Docs` state machine. It decides when a story's book update passes, goes back for repair or goes to a human.
