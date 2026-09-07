---
type: concept
slug: research-prompt-contracts
title: Research prompt contracts
---
# Research prompt contracts

The research workflow renders the eleven templates in
`workflows/src/workhorse_workflows/research/prompts/` from the `Research` state machine. Each
template is a persona contract: it receives only the named workflow arguments, instructs one
bounded decision or write, and returns JSON matching the reply model selected by its render call.
The workflow owns the render bindings; the [research workflow composition root](research-workflow-composition-root.md)
owns their routing, and [workflow prompt static contracts](workflow-prompt-static-contracts.md)
checks that referenced files, variables, and output keys remain aligned.

The templates deliberately refer to repository-local research skills by capability name rather
than embedding implementation instructions. They do not run experiments in an agent turn,
re-grade an artifact, or choose a path outside the decision assigned to their persona.

- code: `workflows/src/workhorse_workflows/research/workflow.py::Research`
- detail: [research workflow documentation boundaries](research-workflow-documentation-boundaries.md)
- detail: [research workflow composition root](research-workflow-composition-root.md)
- detail: [workflow prompt static contracts](workflow-prompt-static-contracts.md)

## Prompt contracts

### `select-next-gate.md`

The autonomous researcher reads the program README ladder, progress log, dependencies, and kill
criteria. It selects the lowest reachable gate that is not `PASS` or `WEAK_PASS`; an exhausted
ladder returns `gate_id: "none"`, while a tripped program kill returns the killed gate and
`program_killed: true`. Its JSON result is `GateSelection`.

### `design-experiment.md`

The scientist reads the gate document, program README, prior progress, and any rework or rescope
context. It produces a falsifiable protocol, spec-file paths, resource declaration, a measured
calibration probe, and an estimate derived from that probe. Scientific rework may change the
protocol but not the hypothesis or frozen threshold; an impossible or contradictory request is
reported as `status: "blocked"`. Its JSON result is `Design`, containing a nested `Probe`.

### `build-experiment.md`

The engineer reads the design's protocol and gate document, implements the experiment and paired
test under the declared code root, and returns both the full argv and the same experiment's `n=1`
argv for rehearsal through the real runner. The command writes `result.json` in its declared cwd.
A fault outside the repository is reported only as `fault_locus: "tooling"` with a named
`component`. Its JSON result is `Build`.

### `triage-overrun.md`

The engineer inspects the detached job directory, logs, heartbeat, and probe estimate. Progress
or an underestimated probe produces `decision: "keep_going"`; a stuck, looping, or unusable job
produces `kill_and_fix` with a specific repair hint. An overrun is never killed merely because a
threshold was crossed. Its JSON result is `TriageResult`.

### `gate-check.md`

The independent lead reads the completed result artifact, supervisor artifact, gate thresholds,
program controls, and kill criteria without seeing or rerunning the measurement. It compares each
metric, checks seeds, controls, completion counts, containment, anti-shortcut flags, and the
zero-weights result, then returns `approved`, `needs_rework`, or `killed`. Its JSON result is
`GateCheck`, with one `FailedCriterion` per failed threshold and nested `AntiShortcutFlags`.

### `record-result.md`

The researcher records the gate verdict in the gate document and progress log, preserving failure
entries. A forced program outcome is recorded under the README's `Program verdict` section; a
killed or forced failure also receives a negative-result finding. Its JSON result is
`RecordResult`.

### `research-lead-review.md`

The research lead reviews a killed gate against its actual experiment, controls, guards, findings,
and program goal. It distinguishes a faithful scientific refutation (`new_direction`) from an
apparatus artifact (`revive`) and supplies either the required apparatus fix or a next-direction
hint. Its JSON result is `LeadReview`.

### `revive-gate.md`

The researcher records a reassessment of a wrongly killed gate, preserves the original negative
finding, marks the gate `REOPENED`, rescopes its corrective plan, and resets dependent gates to
`NOT STARTED`. Its JSON result is `ReviveResult`.

### `define-new-direction.md`

The research lead reads the standing North star, all findings, and progress, then replaces a
justifiably refuted ladder in the same program directory. It records the ruled-out approach,
fresh falsifiable gates, shared controls, and reset progress while preserving the old direction's
record. Its JSON result is `NewDirectionResult`.

### `lead-goal-review.md`

The research lead evaluates an exhausted ladder against the program README's frozen target and
the strongest measured results. It returns `reached`, `banked`, `impossible`, or `extend`, with
the evidence, gap, bankable result, or burden-of-proof details required by that verdict. Its JSON
result is `GoalReview`.

### `extend-program.md`

The researcher appends one next gate to an existing ladder after an `extend` verdict. It preserves
passed gates and the North star, writes the new gate's exact numeric contract and controls, and
updates the README and progress log without implementing experiment code. Its JSON result is
`ExtendResult`.

The reply models and their defaulted fields are documented in [research workflow schemas](research-schemas.md);
the prompt files themselves are the complete source for wording and interpolation context.
