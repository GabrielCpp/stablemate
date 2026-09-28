# qa

The QA lane of the coder workflow. It plans QA for a story, runs it and refuses to believe a pass it cannot check.

## Map

- `flow.py`: the `Qa` state machine and every retry budget that bounds it. It decides whether a QA pass is believed, repaired, triaged or escalated.
- `nodes/`: the non-agent steps only the QA lane calls.
