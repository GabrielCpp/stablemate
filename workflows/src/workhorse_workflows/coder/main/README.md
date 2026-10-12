# main

The main loop of the coder workflow. It works through the stories the launch packed into the worklist, end to end. A failed story never lets the run move on: it parks the run at the operator gate.

A story runs one line: dev, docs, QA, commit. Two detours leave it. A replan re-files the epic's stories when a lane cannot finish the story as written, and a docs lane that cannot document the story is one such lane. A refix sends QA's failures back to the dev owner, and the commit sends back any work left uncommitted, with the paths named. A finished epic is pruned from the queue in its own commit. Once the worklist is empty, a `pr` run opens its PRs and hands them to the ship lane, which gets CI green and leaves the merge to a reviewer. A `commit` run ends there.

## Map

- `flow.py`: the `Coder` state machine. It decides which lane a story goes to next, and when a story, an epic or the run is done.
- `nodes/`: the non-agent steps only the main loop calls.
