# dev

The dev lane of the coder workflow. One dev session owns a work item end to end. It plans, builds, reviews, triages and fixes the work through subagents it picks by strength, and the run checks what it handed back.

The work item is a story or one of its follow-ups. The worklist holds both, and the review's and QA's findings, as the run's one todo list.

## Map

- `flow.py`: the `Dev` state machine. It runs the dev turn, checks the result, and sends whatever failed back to the same session.
- `report.py`: the text the dev owner's next turn reads: a gate's failure, its open findings, and the answers ostler rejected.
- `prompts/dev-story.md`: the dev turn. It names the subagent seats, the reviewer's brief, the triage, the fixes and the answer file.
- `prompts/dev-rework.md`: the dev turn once QA has sent the item back. It extends `dev-story.md` and replaces its opening, its findings and its steps, so the turn starts from QA's findings and fixes each at its cause instead of building from the plan.

## How a work item settles

1. `build` runs the dev turn. The owner files its reviewer's findings in its result, and the run files each one as a worklist item under the turn's review prefix. A `blocked` reply asks the operator, and the answer resumes the same session.
2. `check` records and commits the plan, branches the code repos it names, runs every declared gate, and has ostler settle each open finding against the answer file. A fixed answer whose evidence does not hold, or a "not a defect" decline that names no existing test, stays open. It then reads every affected repo for uncommitted paths that were not dirty when the story began.
3. Anything that failed goes back to `build` as one report. A repair turn fixes only what the report names and runs no new review.
4. Checks that still fail after three repair turns park the run at the operator gate.

The dev turn runs with no timeout. The silence bound and the command cap bound it instead. A compacted session reads the worklist's resume note on its next turn.

An older open finding of the same cause as a newer one is merged into the newest.

The follow-ups a dev turn reports go to the ostler backlog under `Deferred by coder`. The fix lane drains only `Filed by coder`, so no run works them.
