# coder

The `coder` workflow turns epics and stories into committed code. The launch packs the stories into the run's worklist: every epic in order (`epic=all`, the default), one epic (`epic=<name>`), or one story (`story=<slug>`). Each lane is its own state machine, and the main loop runs them over the worklist in order.

The `delivery` parameter decides where the work lands. With `pr`, the default, every item commits on one `feat/` branch, and the run opens one PR per repo it changed, waits for its CI to go green and leaves the merge to a reviewer. With `commit`, every item commits on the branch each repo is on, and no PR opens. In both, each story's commits carry its `Story:` footer.

## Map

- `workflow.py`: the composition root of the `coder` command. It is the one place a lane is registered.
- `docs/`: the lane that folds a finished story into the OKF book and gates that claim against the diff.
- `fix/`: the lane that drains the coder's own filed backlog items, each as a one-AC story.
- `fix_ci/`: the ship lane. It gets the run branch's CI green, and merges it only when given a base.
- `genesis/`: the lane that turns a directory into a repo the main loop will accept.
- `dev/`: the lane where one dev session plans, builds, reviews and fixes a work item through its subagents, and the run checks the result.
- `main/`: the work loop that runs the other lanes over the worklist and delivers the run as commits or as a PR.
- `qa/`: the lane that plans QA for a story, runs it and audits the pass.
- `shared/`: what more than one lane needs: node work, paths, prompt roles and reply schemas.
