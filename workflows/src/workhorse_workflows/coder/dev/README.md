# dev

The dev lane of the coder workflow. One dev session owns a work item end to end. It plans, builds, reviews, triages and fixes the work through subagents it picks by strength, and the run checks what it handed back.

The work item is a story or one of its follow-ups. The worklist holds both, and the review's and QA's findings, as the run's one todo list.

## Map

- `flow.py`: the `Dev` state machine. It runs the dev turn, checks the result, and sends whatever failed back to the same session.
- `report.py`: the text the dev owner's next turn reads: a gate's failure, its open findings, and the answers ostler rejected.
- `prompts/dev-story.md`: the dev turn. It names the subagent seats, the reviewer's brief, the triage, the fixes and the answer file.

## How a work item settles

1. `build` runs the dev turn. The owner files its reviewer's findings in its result, and the run files each one as a worklist item under the turn's review prefix. A `blocked` reply asks the operator, and the answer resumes the same session.
2. `check` records and commits the plan, branches the code repos it names, runs every declared gate, and has ostler settle each open finding against the answer file. It then reads every affected repo for uncommitted paths that were not dirty when the story began.
3. Anything that failed goes back to `build` as one report. A repair turn fixes only what the report names and runs no new review.
4. Checks that still fail after three repair turns park the run at the operator gate.

The dev turn runs with no timeout. The silence bound and the command cap bound it instead. A compacted session reads the worklist's resume note on its next turn.

A follow-up files no follow-ups of its own. The run sends that work to the ostler backlog instead.
