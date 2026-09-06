---
type: concept
slug: research-workflow-composition-root
title: Research workflow composition root
---
# Research workflow composition root

The installed `workhorse-research` command imports `main` from this module. Its `workflow`
registry is the composition boundary for a single gate-at-a-time research machine. A bare run
enters `Research`, whose states select a gate, design and rehearse an experiment, submit a
detached measurement, classify its artifacts, and record a lead's verdict. The state machine
and its response models are documented as deeper layers; deterministic work is delegated to the
[research deterministic node package](research-deterministic-nodes.md).

The registry is rooted at `workhorse_workflows.research`, so every prompt path resolves from this
workflow package. Its dry-run replies make gate selection report an exhausted ladder and make the
goal lead report `reached`; that gives a static dry run a terminating path without inventing an
experiment. The registry registers the research node blueprint, and `main` adapts its default
entry point into the callable required by the console-script installation.

`Research` carries the selected program as checkpointed workflow input. `setup()` clones or uses
the checkout and loads the program context; `labels()` exposes the selected program directory.
`start()` selects the next gate and resets per-gate counters. A named gate proceeds through
`design()`, `build()`, `submit()`, `await_result()`, `collect()`, and `check()`. A missing or
`none` gate enters program-level review instead. A pre-existing kill enters lead review rather
than terminating.

The routing contract separates protocol, apparatus, and verdict ownership. Resource mismatch or
missing calibration returns to design; a repository fault returns to build; tooling faults park
on `BLOCKED.md`; exhausted repair, rescope, or rework allowances go to lead review. A running job
waits on its supervisor wake file, triages overruns without killing by timeout, and collects the
two artifacts only after completion. The check state judges the collected artifact without
rerunning the experiment. Approved results are recorded and published before the next gate;
kills are recorded before lead review.

Lead review can revive the gate and continue, define a new direction and park for operator
authorization, or park when its verdict is not actionable. When the ladder is exhausted,
`goal_review()` accepts `reached`, `banked`, `impossible`, or `extend`; the first three are
recorded by `record_goal()` with the corresponding ledger status, while extension persists its
program-scoped spend and returns to gate selection. No state uses `WorkflowFailed` for a budget
exhaustion or unresolved decision; only `record_goal()` produces a clean terminal result, and a
previously concluded program requires explicit `reauthorize` during setup.

- code: `workflows/src/workhorse_workflows/research/workflow.py::Research`
- code: `workflows/src/workhorse_workflows/research/workflow.py::workflow`
- code: `workflows/src/workhorse_workflows/research/workflow.py::main`
- tests: `workflows/tests/research/test_workflow.py::test_a_gate_designed_built_measured_and_approved_drives_the_program_to_its_goal`
- tests: `workflows/tests/research/test_workflow.py::test_the_checkpoint_carries_the_counters_an_operator_would_edit`
- tests: `workflows/tests/research/test_workflow.py::test_a_resume_rebuilds_the_budget_from_the_checkpoint`

## Methods

### setup

- sig: `setup() -> Program`
- does: clones the requested repository or uses the resolved working checkout
- verify: count(subject="research checkout setups", equals=1)
- does: loads the selected program manifest and rejects a concluded program unless reauthorization is enabled
- verify: count(subject="research program loads", equals=1)
- returns: the loaded `Program` as the workflow context used by later states
- verify: count(subject="research program contexts", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.setup`
- tests: `workflows/tests/research/test_workflow.py::test_a_concluded_program_needs_a_human_before_it_runs_again`

### labels

- sig: `labels() -> dict[str, str]`
- does: labels telemetry with the current program directory
- verify: count(subject="research program telemetry labels", equals=1)
- returns: a dictionary containing the `program` label
- verify: count(subject="research program label dictionaries", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.labels`

### start

- sig: `start(budget: Budget = Budget()) -> Continue`
- does: asks the selector for the next gate from the program ladder
- verify: count(subject="research gate selections", equals=1)
- does: routes an exhausted ladder to program-level goal review
- verify: count(subject="research goal reviews after exhausted ladders", equals=1)
- does: routes a pre-existing killed gate to lead review without recording a new outcome
- verify: count(subject="research pre-existing kill reviews", equals=1)
- does: routes a live gate to design with fresh per-gate counters
- verify: count(subject="research fresh gate designs", equals=1)
- returns: a continuation to the selected next state
- verify: count(subject="research start continuations", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.start`
- tests: `workflows/tests/research/test_workflow.py::test_a_gate_designed_built_measured_and_approved_drives_the_program_to_its_goal`

### design

- sig: `design(gate_id: str, gate_doc_path: str, budget: Budget = Budget(), rework_notes: str = "", failed_criteria: list[FailedCriterion] | None = None, rescope_reason: str = "") -> Continue`
- does: obtains a protocol, resource declaration, estimate, and calibration probe from the scientist
- verify: count(subject="research experiment designs", equals=1)
- does: routes a design exceeding the declared machine envelope back to design for rescoping
- verify: count(subject="research design rescopes", equals=1)
- does: escalates an envelope mismatch to lead review after the rescope allowance is exhausted
- verify: count(subject="research rescope escalations", equals=1)
- does: routes a fitting design to build without executing the experiment
- verify: count(subject="research build handoffs", equals=1)
- returns: a continuation to design or build according to the envelope result
- verify: count(subject="research design continuations", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.design`
- tests: `workflows/tests/research/test_workflow.py::test_a_design_the_machine_cannot_hold_is_rescoped_without_a_person`

### build

- sig: `build(gate_id: str, gate_doc_path: str, design: Design, budget: Budget = Budget(), fix_reason: str = "") -> Continue | Await`
- does: asks the engineer to produce the measurement command and its runner rehearsal command
- verify: count(subject="research experiment builds", equals=1)
- does: parks immediately when the engineer identifies a tooling fault and names its component
- verify: visible(locator="research tooling fault gate")
- does: runs the rehearsal through the real detached runner before submission
- verify: count(subject="research n=1 rehearsals", equals=1)
- does: routes a failed rehearsal through fault-locus repair handling
- verify: count(subject="research rehearsal repairs", equals=1)
- does: hands a successful rehearsal to job submission
- verify: count(subject="research submission handoffs", equals=1)
- returns: a continuation to build, submit, or an operator wait
- verify: count(subject="research build outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.build`
- tests: `workflows/tests/research/test_workflow.py::test_a_rehearsal_that_dies_under_the_runner_never_reaches_submission`

### submit

- sig: `submit(gate_id: str, gate_doc_path: str, design: Design, build: Build, budget: Budget = Budget()) -> Continue | Await`
- does: submits one detached measurement job with the declared resources and calibration units
- verify: count(subject="research detached job submissions", equals=1)
- does: resumes an existing live job through the idempotent submission node rather than launching another job
- verify: count(subject="research idempotent job adoptions", equals=1)
- does: routes a missing calibration probe back to design for rescoping
- verify: count(subject="research missing-probe rescopes", equals=1)
- does: routes other submission faults through engineering repair handling
- verify: count(subject="research submission repairs", equals=1)
- returns: a continuation to waiting, design, or repair handling
- verify: count(subject="research submission outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.submit`
- tests: `workflows/tests/research/test_workflow.py::test_an_estimate_with_no_probe_behind_it_goes_back_to_the_scientist`

### await_result

- sig: `await_result(gate_id: str, gate_doc_path: str, design: Design, build: Build, job_dir: str, budget: Budget = Budget(), seen_multiple: float = 0.0) -> Continue | Await`
- does: watches the detached job and routes finished jobs to collection
- verify: count(subject="research completed job collections", equals=1)
- does: routes each newly crossed overrun threshold to engineering triage
- verify: count(subject="research overrun triages", equals=1)
- does: parks on the supervisor wake file while the job is still running
- verify: visible(locator="research job wake wait")
- returns: a continuation to collection, triage, or an on-machine wait
- verify: count(subject="research job wait outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.await_result`
- tests: `workflows/tests/research/test_workflow.py::test_the_wait_parks_on_the_job_s_own_wake_file_and_asks_nobody_anything`

### triage

- sig: `triage(gate_id: str, gate_doc_path: str, design: Design, build: Build, job_dir: str, overrun_multiple: float = 0.0, budget: Budget = Budget()) -> Continue | Await`
- does: asks the engineer whether an overrun should continue or be killed for repair
- verify: count(subject="research overrun decisions", equals=1)
- does: keeps the job running for every decision other than explicit kill-and-fix
- verify: count(subject="research continued overruns", equals=1)
- does: kills an explicitly rejected runaway job and routes the result through repair handling
- verify: count(subject="research killed overrun repairs", equals=1)
- returns: a continuation to waiting or repair handling
- verify: count(subject="research triage outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.triage`
- tests: `workflows/tests/research/test_workflow.py::test_the_engineer_can_kill_a_runaway_job_and_the_gate_is_rebuilt`

### collect

- sig: `collect(gate_id: str, gate_doc_path: str, design: Design, build: Build, job_dir: str, budget: Budget = Budget()) -> Continue | Await`
- does: classifies the experiment from its result artifact and supervisor cost artifact without a model call
- verify: count(subject="research collected classifications", equals=1)
- does: routes an over-resource result back to design for rescoping
- verify: count(subject="research over-resource rescopes", equals=1)
- does: routes crash and invalid results through fault-locus repair handling
- verify: count(subject="research failed measurement repairs", equals=1)
- does: hands a valid measurement to threshold checking
- verify: count(subject="research gate checks", equals=1)
- returns: a continuation to design, repair handling, or check
- verify: count(subject="research collection outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.collect`
- tests: `workflows/tests/research/test_workflow.py::test_a_crash_in_repo_code_goes_to_the_engineer_with_nobody_in_the_loop`

### check

- sig: `check(gate_id: str, gate_doc_path: str, collected: Collected, budget: Budget = Budget()) -> Continue`
- does: judges the collected artifact against the gate document thresholds without rerunning the experiment
- verify: count(subject="research artifact gate checks", equals=1)
- does: routes approved results to recording
- verify: count(subject="research approved gate recordings", equals=1)
- does: routes killed results to kill recording and lead review
- verify: count(subject="research killed gate recordings", equals=1)
- does: routes a failed result to scientific rework until the rework allowance is exhausted
- verify: count(subject="research scientific reworks", equals=1)
- does: escalates an exhausted rework allowance to lead review
- verify: count(subject="research rework escalations", equals=1)
- returns: a continuation to pass recording, kill recording, rework, or lead review
- verify: count(subject="research check outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.check`
- tests: `workflows/tests/research/test_workflow.py::test_the_measurement_never_runs_inside_the_reviewing_turn`

### record_pass

- sig: `record_pass(gate_id: str, budget: Budget = Budget()) -> Continue`
- does: records the approved gate result
- verify: persists(subject="approved research gate result")
- does: publishes the result branch before selecting another gate
- verify: persists(subject="published research result branch")
- returns: a continuation to start with the current budget
- verify: count(subject="research next-gate continuations", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.record_pass`

### record_kill

- sig: `record_kill(gate_id: str, gate_doc_path: str, failed_criteria: list[FailedCriterion], notes: str, budget: Budget = Budget()) -> Continue`
- does: records the killed gate outcome
- verify: persists(subject="killed research gate result")
- does: routes the recorded kill to lead review instead of terminating
- verify: count(subject="research kill lead reviews", equals=1)
- returns: a continuation to lead review
- verify: count(subject="research kill review continuations", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.record_kill`

### lead_review

- sig: `lead_review(gate_id: str, gate_doc_path: str, failed_criteria: list[FailedCriterion], notes: str, escalation: str = "", budget: Budget = Budget()) -> Continue | Await`
- does: blocks for operator authorization when the program-scoped lead-review allowance is exhausted
- verify: visible(locator="research lead-review cap gate")
- does: asks the research lead to choose revive or new direction when review is allowed
- verify: count(subject="research lead reviews", equals=1)
- does: routes revive to gate revival and new direction to direction definition
- verify: count(subject="research lead verdict routes", equals=1)
- does: blocks an unrecognized lead verdict rather than guessing a route
- verify: visible(locator="research non-actionable lead verdict gate")
- returns: a continuation to revive, new direction, or an operator wait
- verify: count(subject="research lead-review outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.lead_review`
- tests: `workflows/tests/research/test_workflow.py::test_a_lead_verdict_the_loop_cannot_act_on_parks_instead_of_guessing`

### revive

- sig: `revive(gate_id: str, gate_doc_path: str, review: LeadReview, budget: Budget = Budget()) -> Continue`
- does: rescopes a gate the lead judged incorrectly killed
- verify: persists(subject="revived research gate")
- does: persists lead-review spend and publishes the revised result
- verify: persists(subject="research lead-review spend")
- returns: a continuation to start with the updated budget
- verify: count(subject="research revival continuations", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.revive`
- tests: `workflows/tests/research/test_workflow.py::test_a_pre_existing_kill_reaches_the_lead_rather_than_dying`

### new_direction

- sig: `new_direction(gate_id: str, gate_doc_path: str, review: LeadReview, budget: Budget = Budget()) -> Await`
- does: writes the replacement research direction and its new gates
- verify: persists(subject="research replacement direction")
- does: publishes the replacement direction before requesting authorization
- verify: persists(subject="published research replacement direction")
- does: parks until an operator authorizes the new ladder
- verify: visible(locator="research new-direction authorization gate")
- returns: an operator wait that resumes at start
- verify: count(subject="research new-direction waits", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.new_direction`
- tests: `workflows/tests/research/test_workflow.py::test_a_new_direction_always_reaches_a_person_and_is_published_first`

### goal_review

- sig: `goal_review(budget: Budget = Budget()) -> Continue | Await`
- does: asks the lead to judge the program North star after the ladder is exhausted
- verify: count(subject="research goal reviews", equals=1)
- does: routes reached, banked, and impossible verdicts to goal recording
- verify: count(subject="research clean goal verdicts", equals=1)
- does: routes extend to program extension while allowance remains
- verify: count(subject="research program extensions", equals=1)
- does: blocks an exhausted extension allowance or unrecognized verdict
- verify: visible(locator="research goal authorization gate")
- returns: a continuation to goal recording, extension, or an operator wait
- verify: count(subject="research goal-review outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.goal_review`
- tests: `workflows/tests/research/test_workflow.py::test_the_extension_cap_parks_instead_of_halting_the_program`

### extend

- sig: `extend(review: GoalReview, budget: Budget = Budget()) -> Continue`
- does: appends the next gate defined by the goal review
- verify: persists(subject="research extended gate ladder")
- does: persists extension spend and publishes the updated program
- verify: persists(subject="research extension spend")
- returns: a continuation to start on the new lowest non-PASS gate
- verify: count(subject="research extension continuations", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.extend`
- tests: `workflows/tests/research/test_workflow.py::test_extending_writes_the_spend_where_the_next_run_reads_it`

### record_goal

- sig: `record_goal(outcome: str, budget: Budget = Budget()) -> Done`
- does: records the program-level outcome under the `GOAL` result slot
- verify: persists(subject="research goal outcome")
- does: writes the corresponding `reached`, `banked`, or `impossible` ledger status
- verify: persists(subject="research concluded program status")
- does: publishes the concluded program result
- verify: persists(subject="published research goal result")
- returns: a clean terminal `Done` result
- verify: count(subject="research clean terminals", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.record_goal`
- tests: `workflows/tests/research/test_workflow.py::test_an_impossible_verdict_ends_clean_and_concludes_the_program`
