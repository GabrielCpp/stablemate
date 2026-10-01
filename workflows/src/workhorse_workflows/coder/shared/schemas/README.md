# schemas

The models every coder agent reply and node return is validated against, one module per lane.

## Map

- `_base.py`: the base model every coder reply and node return derives from, and the shared `Finding` shape.
- `backlog.py`: the fix lane's backlog models: the drawn item, the seeded story, and the pruned or blocked bullet.
- `ci.py`: the CI loop's models: the repo pick, the checks verdict, the push, the fixer's report and the lap state.
- `dev.py`: the dev lane's models: the plan, its validation, the dispatch list, the implement and fix replies, and the operator gate.
- `docs.py`: the docs lane's models: OKF detection, the context classifier, the author reply, the gates and the loop state.
- `genesis.py`: the genesis lane's models: the target's state, each step's result and the final verdict.
- `okf.py`: the obligation packet's gate result, shared by the docs and QA lanes.
- `pr.py`: the PR boundary's models: the opened PR, the merge, the merge fix and the give-up notes.
- `qa.py`: the QA lane's models: every gate result, every agent reply and the loop state.
- `queue.py`: the main loop's spine models: the epic and story picks, their branches, and what a story's commit recorded.
- `render.py`: the output-contract block a prompt shows, rendered from the model that parses the reply.
- `review.py`: the review lane's models: the two review replies, the settlement gate, the inbox note and the round budgets.
- `story.py`: the story spine's models: the resolved paths, the workspace dirs and the stamped specs count.
- `worktree.py`: the shapes a worktree snapshot and a plan scrub record.
