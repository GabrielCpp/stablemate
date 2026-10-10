# qa

The QA lane of the coder workflow. One QA owner session owns a story's QA end to end. It plans the QA, repairs the context, the stack and the plan, runs it and has a subagent audit the verdict. The run then refuses to believe a pass it cannot check.

QA never fixes the product. A defect the owner proves goes back to the main loop as a finding, and the dev owner fixes it.

## Map

- `flow.py`: the `Qa` state machine. It prepares the story, runs the owner turn, checks the result, and sends whatever failed back to the same session.
- `report.py`: the text the owner's next turn reads: a gate's failure, the failed scenarios, its own findings and the regression suites.
- `prompts/qa-story.md`: the owner turn. Its partials carry the plan contract, the setup brief, the auditor's brief and the dev report.
- `nodes/`: the non-agent steps only the QA lane calls.

## How a story's QA settles

1. `start` clears the last pass's evidence, resolves the story and its repos, builds and validates the OKF context packet, and brings the stack up. A packet or stack that fails becomes the owner's first report. A `qa_plan.py` that lints and validates is handed over as the standing plan.
2. `work` runs the owner turn. A `blocked` reply asks the operator, and the answer resumes the same session.
3. `check` rebuilds the packet and the stack, lints, validates and dry-runs the plan, runs it, and gates the run's evidence, its hygiene and the journey suites the story put at risk.
4. A failed run with findings finishes as `refix` and carries them. A dev target passes instead and carries them as its report.
5. Anything else that failed goes back to `work` as one report. Checks that still fail after three repair turns park the run at the operator gate.

The owner turn runs with no timeout. The silence bound and the command cap bound it instead.

`stop_at_first_verdict` turns the first red run into the verdict. A blocked run still goes back to the owner, because it says nothing about the product.
