# main

The main loop of the coder workflow. It works through one epic's stories end to end, or one named story.

## Map

- `flow.py`: the `Coder` state machine. It decides which lane a story goes to next, and when a story, an epic or its PR is done.
- `nodes/`: the non-agent steps only the main loop calls.
