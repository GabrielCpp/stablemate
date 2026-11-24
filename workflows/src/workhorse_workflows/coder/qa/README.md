# qa

The QA lane of the coder workflow. One QA owner session owns a story's QA end to end. It selects the scenarios from the claims the books could not state, runs them, debugs each failure and records the result in `qa.md` and `jira-comment.md`, with no subagent seat and no audit. The scored run is the verdict, and the run then refuses to believe a pass it cannot check.

QA never fixes the product. A defect the owner proves goes back to the main loop as a finding, and the dev owner fixes it.

## How a story's QA settles

1. `start` clears the last pass's evidence, resolves the story and its repos, and brings the stack up from the `stack.yml` of the story's service books. A stack that fails becomes the owner's first report. A `qa_plan.py` that lints is handed over as the standing plan. A story whose books judged every claim passes with no owner turn.
2. `work` runs the owner turn. A `blocked` reply asks the operator, and the answer resumes the same session.
3. `check` rechecks the stack, lints the plan, runs it, and gates the run's evidence, its hygiene and the journey suites the story put at risk.
4. A failed run goes to the owner of each scenario's side. A fixture step that cannot start is the environment's, and the run parks at the operator gate. A claim that failed on a held condition is the product's, and it finishes as `refix` with one finding per scenario, beside the owner's own. A dev target passes instead and carries them as its report. A fixture step that failed or a condition that read back false is the book's, and it goes back to the owner to repair. A scenario with no side goes back to the owner to classify. A scenario that ran past its wall-clock ceiling is killed by ostler and parks the run at the operator gate, because the operator decides whether the scenario is too long or the app hangs.
5. Anything else that failed goes back to `work` as one report. Checks that still fail after three repair turns park the run at the operator gate.

The owner turn runs for at most `turn_minutes` minutes (180 by default). A turn still running then is cut and asks the operator, and the answer resumes it on the same conversation. The silence bound and the command cap bound the turn within that.

`stop_at_first_verdict` turns the first red run into the verdict. A blocked run and a red on the book's side still go back to the owner, because neither says anything about the product. A rerun with no owner turn routes its red the same way, and a scenario with no side goes to dev.
