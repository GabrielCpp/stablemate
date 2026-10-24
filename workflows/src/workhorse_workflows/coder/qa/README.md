# qa

The QA lane of the coder workflow. One QA owner session owns a story's QA end to end. It plans the QA, repairs the context, the stack and the plan, runs it and has a subagent audit the verdict. The run then refuses to believe a pass it cannot check.

QA never fixes the product. A defect the owner proves goes back to the main loop as a finding, and the dev owner fixes it.

## Map

- `flow.py`: the `Qa` state machine. It prepares the story, runs the owner turn, checks the result, and sends whatever failed back to the same session.
- `report.py`: the text the owner's next turn reads: a gate's failure, the failed scenarios, its own findings and the regression suites.
- `sides.py`: the side each failed scenario sits on, read from the cause ostler gave its failed checks.
- `prompts/qa-story.md`: the owner turn. Its partials carry the plan contract, the setup brief, the auditor's brief and the dev report.
- `nodes/`: the non-agent steps only the QA lane calls.

## How a story's QA settles

1. `start` clears the last pass's evidence, resolves the story and its repos, builds and validates the OKF context packet, and brings the stack up. A packet or stack that fails becomes the owner's first report. A `qa_plan.py` that lints and validates is handed over as the standing plan.
2. `work` runs the owner turn. A `blocked` reply asks the operator, and the answer resumes the same session.
3. `check` rebuilds the packet and the stack, lints, validates and dry-runs the plan, runs it, and gates the run's evidence, its hygiene and the journey suites the story put at risk.
4. A failed run goes to the owner of each scenario's side. A fixture step that cannot start is the environment's, and the run parks at the operator gate. A claim that failed on a held condition is the product's, and it finishes as `refix` with one finding per scenario, beside the owner's own. A dev target passes instead and carries them as its report. A fixture step that failed or a condition that read back false is the book's, and it goes back to the owner to repair. A scenario with no side goes back to the owner to classify.
5. Anything else that failed goes back to `work` as one report. Checks that still fail after three repair turns park the run at the operator gate.
6. A required obligation the book gives no runnable check is deferred. The evidence gate skips it, as the plan lint does. A passed story files each page that owes such a check as a record on the debt register, in the workspace repository that owns the page, area `book`, one record per page and one artifacts commit per run. The fix lane drains only `Filed by coder`, so these wait for the book and never hold a story's commit.

The owner turn runs with no timeout. The silence bound and the command cap bound it instead.

`stop_at_first_verdict` turns the first red run into the verdict. A blocked run and a red on the book's side still go back to the owner, because neither says anything about the product. A rerun with no owner turn routes its red the same way, and a scenario with no side goes to dev.
