# coder

The `coder` workflow turns epics and stories into committed code. The launch packs the stories into the run's worklist: every epic in order (`epic=all`, the default), one epic (`epic=<name>`), or one story (`story=<slug>`). Each lane is its own state machine, and the main loop runs them over the worklist in order.

The `delivery` parameter decides where the work lands. With `pr`, the default, every item commits on one `feat/` branch, and the run opens one PR per repo it changed, waits for its CI to go green and leaves the merge to a reviewer. With `commit`, every item commits on the branch each repo is on, and no PR opens. In both, each story's commits carry its `Story:` footer.
