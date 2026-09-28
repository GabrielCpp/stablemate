# dev

The dev lane of the coder workflow. It plans a story, gates the plan, then implements and repairs it one service at a time.

## Map

- `flow.py`: the `Dev` state machine. It decides the order of the plan, gate, implement and repair turns.
- `nodes.py`: the turns the dev lane takes, the budgets that bound them, and where a block goes once a budget runs out.
