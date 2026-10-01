# shared

What more than one coder lane needs. Code that only one lane calls belongs in that lane's directory.

## Map

- `backlog.py`: the repo backlog's `Filed by coder` section: what the coder files into it, and what the fix lane drains out.
- `blueprint.py`: the one `Blueprint` every coder node registers against.
- `branches.py`: the epic and story branches: their names, cutting them, the claim ledger and catching up with base.
- `ci.py`: the CI loop's work: which repo is next, what its Actions runs said, and the push of a fix.
- `commits.py`: the Conventional Commit subject and trailers of every commit the coder writes.
- `contract.py`: the one rule for what counts as a service the planner can target.
- `conversation.py`: the story's backbone session chain, recycled when it is full.
- `dev.py`: a story's status and the operator's answer file.
- `docs.py`: the docs lane's work: whether a book exists, which doc nodes a diff touches, and the fail-closed grounding gate.
- `escalation.py`: the body a coder lane writes when it stops and asks a human.
- `failure.py`: the one failure shape the repair role reads, whatever gate produced it.
- `okf.py`: the diff-to-OKF obligation packet, its check, and the memo that skips a rebuild when its inputs have not changed.
- `paths.py`: where every coder artifact lives: repo roots, epics, the backlog, the feature book and operator context files.
- `plan.py`: a story's plan context: loading `plan-context.json`, projecting it, and the dispatch order.
- `provenance.py`: which commits and files belong to a story.
- `qa_support.py`: a re-export of `kit/qa/support.py` for older coder call sites. New code imports the kit module.
- `queue.py`: the epic and story queue: which epic and story run next, and what is set aside.
- `resolution.py`: the resolver half of an operator gate, which tries to answer a block before the run parks on it.
- `review.py`: the review lane's work: where review turns run, the settlement gate, and the operator inbox poll.
- `roles.py`: which prompt body and model a role resolves to, with the repo's own prompts ahead of the base library.
- `scenarios.py`: the plan's Test Scenarios list, and which of its scenarios fall to the QA lane.
- `schemas/`: the reply and return models every coder lane validates against.
- `service_gates.py`: each service's declared gate commands, in order, and running them.
- `story.py`: which story a run is on, its workspace dirs and its spec stamps.
- `story_commit.py`: the clean-tree check, the commit that records a passed story, and its stamp.
- `story_status.py`: the story's Status line. It is the single place the coder records an outcome.
- `stubs.py`: what the coder's gates return under `--dry-run`.
- `worktree.py`: what the worktrees held before a turn, and what changed since.
