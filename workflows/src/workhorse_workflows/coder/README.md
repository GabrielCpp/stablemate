# coder

The `coder` workflow turns epics and stories into merged code. The launch packs the stories into the run's worklist: every epic in order (`epic=all`, the default), one epic (`epic=<name>`), or one story (`story=<slug>`). Each lane is its own state machine, and the main loop runs them over the worklist in order.

## Map

- `workflow.py`: the composition root of the `coder` command. It is the one place a lane is registered.
- `docs/`: the lane that folds a finished story into the OKF book and gates that claim against the diff.
- `fix/`: the lane that drains the coder's own filed backlog items, each as a one-AC story.
- `fix_ci/`: the ship lane. It gets each epic branch's CI green, then merges the epic and resolves what keeps it from merging.
- `genesis/`: the lane that turns a directory into a repo the main loop will accept.
- `dev/`: the lane where one dev session plans, builds, reviews and fixes a work item through its subagents, and the run checks the result.
- `main/`: the epic and story loop that runs the other lanes in a line and opens the PR the ship lane lands.
- `qa/`: the lane that plans QA for a story, runs it and audits the pass.
- `shared/`: what more than one lane needs: node work, paths, prompt roles and reply schemas.
