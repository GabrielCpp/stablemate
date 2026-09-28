# coder

The `coder` workflow turns a queue of epics and stories into merged code. Each lane is its own state machine, and the main loop runs them in order.

## Map

- `workflow.py`: the composition root of the `coder` command. It is the one place a lane is registered.
- `dev/`: the lane that plans a story and implements it one service layer at a time.
- `docs/`: the lane that folds a finished story into the OKF book and gates that claim against the diff.
- `fix/`: the lane that drains the coder's own filed backlog items, each as a one-AC story.
- `fix_ci/`: the lane that gets each epic branch's CI green.
- `genesis/`: the lane that turns a directory into a repo the main loop will accept.
- `main/`: the epic and story loop that runs the other lanes and owns the PR boundary.
- `qa/`: the lane that plans QA for a story, runs it and audits the pass.
- `review/`: the lane that reviews a story's implementation until every finding is settled.
- `shared/`: what more than one lane needs: node work, paths, prompt roles and reply schemas.
