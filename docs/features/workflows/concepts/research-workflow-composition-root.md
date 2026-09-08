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
workflow package. Its dry-run replies make gate selection report an exhausted ladder, the program
review wave the gate through, the program recharter write the change, and the goal lead report
`reached`; that gives a static dry run a terminating path without inventing an experiment. The
registry registers the research node blueprint, and `main` adapts its default entry point into the
callable required by the console-script installation.

`Research` carries the selected program as checkpointed workflow input. `setup()` clones or uses
the checkout and loads the program context; `labels()` exposes the selected program directory.
`start()` selects the next gate and resets per-gate counters. A named gate proceeds through
`design()`, `build()`, `submit()`, `await_result()`, `collect()`, and `check()`. A missing or
`none` gate enters program-level review instead. A pre-existing kill enters program review with
origin `kill` rather than terminating, and a periodic check (when the computed dossier triggers
it) enters program review with origin `periodic`.

The routing contract separates protocol, apparatus, and verdict ownership. Resource mismatch or
missing calibration returns to design; a repository fault returns to build; tooling faults park
on `BLOCKED.md`; exhausted repair, rescope, or rework allowances enter program review with origin
`escalation`. A running job waits on its supervisor wake file, triages overruns without killing by
timeout, and collects the two artifacts only after completion. The check state judges the collected
artifact without rerunning the experiment. Approved results are recorded and published before the
next gate; kills are recorded before program review with origin `kill`.

Lead review can revive the gate (which then re-enters program review with origin `revive`) or
define a new direction. A new direction no longer always reaches a person: it checks the written
target's resolvability in code, and a target that clears it starts at once; one that does not goes
into the recharter fix loop. Both states park when their verdict is not actionable. When the
ladder is exhausted, `goal_review()` accepts `reached`, `banked`, `impossible`, or `extend`; the
first three are recorded by `record_goal()` with the corresponding ledger status, while extension
persists its program-scoped spend and returns to gate selection. No state uses `WorkflowFailed`
for a budget exhaustion or unresolved decision; only `record_goal()` produces a clean terminal
result, and a previously concluded program requires explicit `reauthorize` during setup.

- code: `workflows/src/workhorse_workflows/research/workflow.py::Research`
- code: `workflows/src/workhorse_workflows/research/workflow.py::workflow`
- code: `workflows/src/workhorse_workflows/research/workflow.py::main`
- tests: `workflows/tests/research/test_workflow.py::test_a_gate_designed_built_measured_and_approved_drives_the_program_to_its_goal`
- tests: `workflows/tests/research/test_workflow.py::test_the_checkpoint_carries_the_counters_an_operator_would_edit`
- tests: `workflows/tests/research/test_workflow.py::test_a_resume_rebuilds_the_budget_from_the_checkpoint`
- detail: [Workflow kit tools](workflow-kit-tools.md)
- detail: [Workflow kit git](workflow-kit-git.md)
- detail: [Workflow kit workspace](workflow-kit-workspace.md)
- detail: [Workflow kit paths](workflow-kit-paths.md)
- detail: [Research main entry point views](research-main-entry-point-views.md)
- detail: [research workflow documentation boundaries](research-workflow-documentation-boundaries.md)
- detail: [Research deterministic nodes](research-deterministic-nodes.md)

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
- does: builds the program dossier deterministically and passes its summary to the gate selector
- verify: count(subject="research dossier builds", equals=1)
- does: asks the selector for the next gate from the program ladder
- verify: count(subject="research gate selections", equals=1)
- does: routes an exhausted ladder to program-level goal review
- verify: count(subject="research goal reviews after exhausted ladders", equals=1)
- does: routes a pre-existing killed gate to program review with origin `kill`
- verify: count(subject="research pre-existing kill program reviews", equals=1)
- does: routes a periodic review (when the dossier triggers one) to program review with origin `periodic`
- verify: count(subject="research periodic program reviews", equals=1)
- does: routes a live gate to design with fresh per-gate counters
- verify: count(subject="research fresh gate designs", equals=1)
- returns: a continuation to the selected next state
- verify: count(subject="research start continuations", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.start`
- tests: `workflows/tests/research/test_workflow.py::test_a_gate_designed_built_measured_and_approved_drives_the_program_to_its_goal`
- tests: `workflows/tests/research/test_workflow.py::test_a_periodic_review_fires_after_enough_gates_and_the_clock_restarts`

### design

- sig: `design(gate_id: str, gate_doc_path: str, budget: Budget = Budget(), rework_notes: str = "", failed_criteria: list[FailedCriterion] | None = None, rescope_reason: str = "") -> Continue`
- does: obtains a protocol, resource declaration, estimate, and calibration probe from the scientist
- verify: count(subject="research experiment designs", equals=1)
- does: routes a design exceeding the declared machine envelope back to design for rescoping
- verify: count(subject="research design rescopes", equals=1)
- does: escalates an envelope mismatch to program review with origin `escalation` after the rescope allowance is exhausted
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
- does: escalates a probe-less design to program review with origin `escalation` after the rescope allowance is exhausted
- verify: count(subject="research missing-probe escalations", equals=1)
- returns: a continuation to waiting, design, repair handling, or program review
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
- does: escalates a sustained over-resource result to program review with origin `escalation` after the rescope allowance is exhausted
- verify: count(subject="research over-resource escalations", equals=1)
- does: routes crash and invalid results through fault-locus repair handling
- verify: count(subject="research failed measurement repairs", equals=1)
- does: hands a valid measurement to threshold checking
- verify: count(subject="research gate checks", equals=1)
- returns: a continuation to design, repair handling, check, or program review
- verify: count(subject="research collection outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.collect`
- tests: `workflows/tests/research/test_workflow.py::test_a_crash_in_repo_code_goes_to_the_engineer_with_nobody_in_the_loop`

### check

- sig: `check(gate_id: str, gate_doc_path: str, collected: Collected, budget: Budget = Budget()) -> Continue`
- does: judges the collected artifact against the gate document thresholds without rerunning the experiment
- verify: count(subject="research artifact gate checks", equals=1)
- does: routes approved results to recording
- verify: count(subject="research approved gate recordings", equals=1)
- does: routes killed results to kill recording, which then forwards them to program review with origin `kill`
- verify: count(subject="research killed gate recordings", equals=1)
- does: routes a failed result to scientific rework until the rework allowance is exhausted
- verify: count(subject="research scientific reworks", equals=1)
- does: escalates an exhausted rework allowance to program review with origin `escalation`
- verify: count(subject="research rework escalations", equals=1)
- returns: a continuation to pass recording, kill recording, rework, or program review
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
- does: routes the recorded kill to program review with origin `kill` instead of terminating
- verify: count(subject="research kill program reviews", equals=1)
- returns: a continuation to program review
- verify: count(subject="research kill review continuations", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.record_kill`
- tests: `workflows/tests/research/test_workflow.py::test_a_kill_reaches_the_program_lead_before_the_gate_lead`

### lead_review

- sig: `lead_review(gate_id: str, gate_doc_path: str, failed_criteria: list[FailedCriterion], notes: str, escalation: str = "", budget: Budget = Budget(), dossier: str = "") -> Continue | Await`
- does: blocks for operator authorization when the program-scoped lead-review allowance is exhausted
- verify: visible(locator="research lead-review cap gate")
- does: renders the program dossier when none was carried in, and passes it to the lead
- verify: count(subject="research lead-review dossier renders", equals=1)
- does: asks the research lead to choose revive or new direction when review is allowed
- verify: count(subject="research lead reviews", equals=1)
- does: routes revive back through program review with origin `revive`, and new direction to direction definition
- verify: count(subject="research lead verdict routes", equals=1)
- does: blocks an unrecognized lead verdict rather than guessing a route
- verify: visible(locator="research non-actionable lead verdict gate")
- returns: a continuation to revive, new direction, or an operator wait
- verify: count(subject="research lead-review outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.lead_review`
- tests: `workflows/tests/research/test_workflow.py::test_a_lead_verdict_the_loop_cannot_act_on_parks_instead_of_guessing`
- tests: `workflows/tests/research/test_workflow.py::test_a_kill_reaches_the_program_lead_before_the_gate_lead`

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

- sig: `new_direction(gate_id: str, gate_doc_path: str, review: LeadReview, budget: Budget = Budget(), dossier: str = "") -> Continue`
- does: writes the replacement research direction and its new gates
- verify: persists(subject="research replacement direction")
- does: publishes the replacement direction regardless of what the resolvability check says
- verify: persists(subject="published research replacement direction")
- does: runs the written target through the in-code resolvability check
- verify: count(subject="research new-direction resolvability checks", equals=1)
- does: continues straight to start when the written target is resolvable on its own eval
- verify: count(subject="research new-direction direct continuations", equals=1)
- does: routes an unresolvable written target to recharter with the failure statement
- verify: count(subject="research new-direction recharter routes", equals=1)
- returns: a continuation to start or recharter
- verify: count(subject="research new-direction continuations", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.new_direction`
- tests: `workflows/tests/research/test_workflow.py::test_a_new_direction_is_checked_in_code_and_parks_only_when_its_target_cannot_resolve`
- tests: `workflows/tests/research/test_workflow.py::test_a_new_direction_with_a_resolvable_target_starts_with_nobody_in_the_loop`

### program_review

- sig: `program_review(origin: str, gate_id: str, gate_doc_path: str, failed_criteria: list[FailedCriterion], notes: str, escalation: str = "", review: LeadReview | None = None, budget: Budget = Budget()) -> Continue | Await`
- does: blocks for operator authorization when the program-scoped program-review allowance is exhausted
- verify: visible(locator="research program-review cap gate")
- does: builds the program dossier deterministically and renders it for the program lead
- verify: count(subject="research program-review dossier renders", equals=1)
- does: asks the program lead for a verdict among `continue`, `probe_first`, `score_from_cache`, `recharter`, `bank`, `stop_negative`, or `operator`
- verify: count(subject="research program reviews", equals=1)
- does: routes a `continue` verdict to `revive` (origin `revive`), `design` (origin `periodic`), or `lead_review` (other origins)
- verify: count(subject="research program-review continue routes", equals=1)
- does: routes `probe_first`, `score_from_cache`, or `recharter` verdicts to `recharter`
- verify: count(subject="research program-review recharter routes", equals=1)
- does: parks a `recharter` verdict when the recharter cap is exhausted
- verify: visible(locator="research recharter cap gate")
- does: routes a `bank` verdict to `record_goal` with the banked outcome
- verify: count(subject="research program-review bank routes", equals=1)
- does: routes a `stop_negative` verdict to `record_goal` with the impossible outcome
- verify: count(subject="research program-review stop-negative routes", equals=1)
- does: parks an `operator` verdict or any verdict the loop cannot act on
- verify: visible(locator="research program-review operator gate")
- returns: a continuation to revive, design, lead_review, recharter, record_goal, or an operator wait
- verify: count(subject="research program-review outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.program_review`
- tests: `workflows/tests/research/test_workflow.py::test_a_kill_reaches_the_program_lead_before_the_gate_lead`
- tests: `workflows/tests/research/test_workflow.py::test_the_program_lead_can_bank_a_killed_program_from_the_kill`
- tests: `workflows/tests/research/test_workflow.py::test_a_stop_negative_verdict_records_the_program_impossible`
- tests: `workflows/tests/research/test_workflow.py::test_a_program_verdict_the_loop_cannot_act_on_parks_instead_of_guessing`
- tests: `workflows/tests/research/test_workflow.py::test_the_program_review_cap_parks_and_an_answer_authorizes_one_more`

### recharter

- sig: `recharter(review: ProgramReview, budget: Budget = Budget(), attempt: int = 0, resolvability_failure: str = "") -> Continue | Await`
- does: applies a program-level verdict (probe gate, cache directive, or rewritten frozen target) to the program folder in place
- verify: count(subject="research recharter applications", equals=1)
- does: runs the in-code resolvability check on a rewritten frozen target
- verify: count(subject="research recharter resolvability checks", equals=1)
- does: retries the program-recharter turn once when the target is unresolvable
- verify: count(subject="research recharter retries", equals=1)
- does: parks on the operator's `Frozen target` table when the target is still unresolvable after the retry
- verify: visible(locator="research recharter retry gate")
- does: persists the program spend (recharter-budget spent only when a target was rewritten) and publishes the result
- verify: persists(subject="research recharter spend")
- returns: a continuation to start or an operator wait
- verify: count(subject="research recharter outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/research/workflow.py::Research.recharter`
- tests: `workflows/tests/research/test_workflow.py::test_a_recharter_is_checked_in_code_and_spends_its_own_budget`
- tests: `workflows/tests/research/test_workflow.py::test_a_recharter_whose_numbers_do_not_clear_seed_noise_is_retried_once_then_parked`
- tests: `workflows/tests/research/test_workflow.py::test_the_recharter_cap_parks_with_the_proposed_target`

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
