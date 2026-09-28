# story_split

The machine that splits one named epic into stories and converges its coverage before any story is written.

## Map

- `flow.py`: the story-split state machine and its rework and resolve budgets.
- `nodes/`: the step that records a passing coverage review.
- `schemas.py`: the terminal value and review receipt of the story-split flow.
