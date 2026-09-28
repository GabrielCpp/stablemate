# fix

The fix lane of the coder workflow. It drains the items the coder filed into the backlog.

## Map

- `flow.py`: the `Fix` state machine. It drains the `Filed by coder` items one at a time, each as a committed one-AC story.
