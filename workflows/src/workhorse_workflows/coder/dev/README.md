# dev

The dev lane of the coder workflow. One dev session owns a work item end to end, in three phase turns on one conversation: plan, build and review. The plan turn makes every design call on the strongest model. The build and review turns follow the plan on a cheaper model when an `advisor` subagent is there to answer the design calls they still meet, and on the strongest model otherwise. The run checks what each turn handed back.

The work item is a story or one of its follow-ups. The worklist holds both, and the review's and QA's findings, as the run's one todo list.

## Map

- `flow.py`: the `Dev` state machine. It runs the phase turns, checks the result, and sends whatever failed back to the review phase on the same session.
- `report.py`: the text the dev owner's next turn reads: a gate's failure, its open findings, the answers ostler rejected, the departures with no advice and the declines with no consult.
- `prompts/dev-plan.md`: the plan turn. It writes and commits the plan files and no product code.
- `prompts/dev-build.md`: the build turn. It builds the plan, walks the criteria, and reports every departure from the plan with the advisor's answer.
- `prompts/dev-review.md`: the review turn. It names the reviewer's brief, the triage, the fixes and the answer file, and gives QA's findings their own section.
- `prompts/dev-follow-up.md`: the short note a phase gets instead of its brief when it continues on the conversation it last ran on. It names the file the brief is kept at.
- `prompts/_dev-*.md`: the inputs, standards, scope and result sections the phase briefs share.

## How a work item settles

1. `start` forgets which conversation each phase was briefed on. A work item QA sent back goes to `review`. Any other goes to `plan`.
2. `plan` writes the plan, and `build` builds it. With an advisor offered, a departure from the plan that carries no advice sends the build back.
3. `review` has a fresh reviewer judge the diff, and fixes and answers every finding. The owner files its reviewer's findings in its result, and the run files each one as a worklist item under the turn's review prefix. A `blocked` reply from any phase asks the operator, and the answer resumes that phase on the same session.
4. `check` records and commits the plan, branches the code repos it names, runs every declared gate, and has ostler settle each open finding against the answer file. A fixed answer whose evidence does not hold, or a "not a defect" decline that names no existing test, stays open. With an advisor offered, a decline with no consult on file reopens. It then reads every affected repo for uncommitted paths that were not dirty when the story began.
5. Anything that failed goes back to `review` as one report. A repair turn fixes only what the report names and runs no new review.
6. Checks that still fail after three repair turns park the run at the operator gate.

Each phase writes its full brief to the run's state before its turn. A phase that continues on the conversation it last ran on gets the follow-up note instead, which points at that file. The phase turns run with no timeout. The silence bound and the command cap bound them instead. A compacted session reads the worklist's resume note and the brief's path on its next turn.

An older open finding of the same cause as a newer one is merged into the newest.

The follow-ups a dev turn reports become records in the debt register, one `record.md` folder each under the artifacts repo's `backlog/<repo>/<area>/<id>/`. The fix lane drains only `Filed by coder`, so no run works them.
