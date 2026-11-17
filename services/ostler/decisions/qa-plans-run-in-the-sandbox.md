story: none
date: 2026-11-17
elements: LintPlan, LintBadPlan, ValidatePlan, ValidateBadPlan, RunPlan, RunBadPlan, ReportRun, ReplayRun, ReadLedger, CutFrames, StartSession, RecordStep, RecordAssertion, StopSession

`ostler qa` runs against two plans the sandbox holds: `plans/qa_plan.py`, which is sound, and `plans/bad/qa_plan.py`,
which imports `os` and claims coverage no check binds. The sound plan has one scenario on a `cli` target with the
`fixture` mechanism and one check that does not touch a process, a network or a browser. A plan with a `live` mechanism,
a daemon, a Playwright or Maestro target, or a recording is not played, so `qa frames` is only ever refused, and the
files under `ostler/ostler/qa/harness/` that drive a browser or a device stay open in `QUESTIONS.md`.

The lint runs before the validation and the run, so the bad plan is refused with the lint's words by `lint`,
`validate` and `run` alike. The unbound claim in the same plan would be refused by the validation, and the book does
not play it apart.

A batch run writes the ledger, one assertion file, the evidence and the report beside the plan. If a session is open it
removes the session file, which the cell `run the plan` in the open scene shows. `qa report` writes the report when the
spec has a ledger and refuses when it has none. `qa stop` prints how many assertions passed and always `0 steps`, because
the step count the stop prints is the live-mechanism steps. `qa step` runs its command and records it, and the book plays
`echo hi`.
