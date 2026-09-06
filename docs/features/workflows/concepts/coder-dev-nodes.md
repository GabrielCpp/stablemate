---
type: concept
slug: coder-dev-nodes
title: Coder development nodes
---
# Coder development nodes

The development flow keeps its reusable routing and agent-call mechanics in `nodes.py`. These
functions do not implement a service themselves: they select the next layer, preserve the
story conversation budget, turn deterministic gate failures into one repair path, and route
unresolvable decisions to the operator instead of terminating the run. A plan block and an
implementation block use separate routing counters, while repair laps share one per-layer
budget across all gates. The resolver may apply only a decision grounded in an existing record;
an unresolved question remains an operator gate, and a block can recur after the resolver budget
is spent.

- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py`
- tests: `workflows/tests/coder/dev/test_flow.py::test_plans_stamps_branches_and_implements_every_layer`
- detail: [coder development flow](../flows/coder-dev.md)

## Fields

### UNBOUNDED
- type: `float`
- default: `infinity`
- required: true
- semantics: the resolver turn has no timeout so it can finish an operator investigation
- verify: count(subject="unbounded resolver timeout", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::UNBOUNDED`

### MAX_FIX_LAPS
- type: `int`
- default: `3`
- required: true
- semantics: a layer receives at most three repair laps before the implementation gate
- verify: count(subject="development repair-lap limit", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::MAX_FIX_LAPS`

### MAX_SESSION_TURNS
- type: `int`
- default: `8`
- required: true
- semantics: the story backbone is recycled after eight implementation or repair turns
- verify: count(subject="development session-turn limit", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::MAX_SESSION_TURNS`

### MAX_VALIDATE_REWORKS
- type: `int`
- default: `3`
- required: true
- semantics: invalid service-path plans receive three path-repair turns before escalation
- verify: count(subject="development path-rework limit", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::MAX_VALIDATE_REWORKS`

### MAX_PLAN_BLOCKS
- type: `int`
- default: `3`
- required: true
- semantics: the automatic resolver gets three block trips before later trips go directly to the operator
- verify: count(subject="development resolver-trip limit", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::MAX_PLAN_BLOCKS`

### HUMAN_MODES
- type: `frozenset[str]`
- default: `human | operator`
- required: true
- semantics: these operator modes bypass automatic resolution and await the story context file
- verify: count(subject="direct human operator modes", equals=2)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::HUMAN_MODES`

## Methods

### repair_chain
- sig: `repair_chain(flow: Dev, worklist: str) -> str`
- does: returns a story-scoped session key for the requested plan-repair worklist
- does: keeps path repair and block repair on separate conversation keys
- returns: `plan-<worklist>:<story-slug>`
- verify: count(subject="story-scoped repair chains", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::repair_chain`

### spend
- sig: `spend(flow: Dev, lap: Lap) -> Lap`
- does: increments the story backbone turn count and recycles the conversation when the session limit is reached
- returns: a copied `Lap` with the updated session-turn count
- verify: count(subject="development session turns", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::spend`
- tests: `workflows/tests/coder/dev/test_flow.py::test_plans_stamps_branches_and_implements_every_layer`

### ends
- sig: `ends(flow: Dev, result: DevResult, session_turns: int = 0) -> Done`
- does: resets both plan-repair conversations before returning the development result
- does: preserves the backbone session-turn count on the returned result for the next lane
- returns: a terminal `Done` carrying the supplied `DevResult` and session-turn count
- verify: count(subject="development flow terminal results", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::ends`

### current_layer
- sig: `current_layer(flow: Dev) -> DispatchEntry`
- does: reads the selected dispatch entry from the recorded layer-selection output
- returns: the current `DispatchEntry`
- verify: count(subject="current development layer reads", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::current_layer`

### escalate
- sig: `escalate(flow: Dev, notes: str, number: int, result: OperatorResolution | None = None, block_kind: str = "plan", where: str = "the plan stage", findings: Sequence[Finding] = ()) -> OperatorGate`
- does: composes the operator gate body from the block, resolver investigation, and findings
- does: preserves resolver evidence and the concrete block kind and location in the gate
- returns: an `OperatorGate` whose body preserves the investigation for the operator
- verify: count(subject="development escalation bodies", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::escalate`
- tests: `workflows/tests/coder/dev/test_flow.py::test_an_escalating_resolver_leaves_its_note_for_the_human`

### resolver_turn
- sig: `resolver_turn(flow: Dev, block_kind: str, notes: str) -> OperatorResolution`
- does: asks the shared resolver to investigate the block with the configured smart power and no timeout
- does: supplies the story workspace and documentation root as resolver context
- returns: the resolver's structured `OperatorResolution`
- verify: count(subject="development resolver turns", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::resolver_turn`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_resolver_that_grounds_its_answer_settles_the_block_without_a_person`

### gate_plan
- sig: `gate_plan(flow: Dev, result: object, notes: str, plan_blocks: int) -> Continue | Await`
- does: sends a plan block to the resolver while automatic resolution is enabled and its budget remains
- does: awaits the operator directly in human or operator mode
- does: awaits the operator directly after three resolver trips without imposing a cap on later human blocks
- returns: a continuation to plan resolution or an await on story context
- verify: count(subject="plan-block routing arms", equals=3)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::gate_plan`
- tests: `workflows/tests/coder/dev/test_flow.py::test_human_operator_modes_wait_on_the_story_context_file`
- tests: `workflows/tests/coder/dev/test_a_service_path_nobody_can_repair_never_gives_up`

### repair_or_escalate
- sig: `repair_or_escalate(flow: Dev, report: FailureReport, notes: str, where: str, index: int, impl_blocks: int, lap: Lap) -> Continue | Await`
- does: routes a dirty gate to another repair lap while the shared lap budget remains
- does: routes the exhausted repair budget to the implementation operator gate
- verify: count(subject="development repair routing arms", equals=2)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::repair_or_escalate`
- tests: `workflows/tests/coder/dev/test_a_gate_no_repair_lap_can_satisfy_never_gives_up_either`

### gate_impl
- sig: `gate_impl(flow: Dev, result: CoderResult, notes: str, index: int, where: str, impl_blocks: int, lap: Lap) -> Continue | Await`
- does: sends a blocked implementation or exhausted repair to resolution when automatic resolution remains available
- does: routes directly to the operator in human or operator mode
- does: routes directly to the operator after the resolver budget is spent while retaining actionable findings
- returns: a resolver continuation or an operator await
- verify: count(subject="implementation-block routing arms", equals=3)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::gate_impl`
- tests: `workflows/tests/coder/dev/test_an_implementation_turn_that_says_it_cannot_reaches_the_operator`
- tests: `workflows/tests/coder/dev/test_an_implementation_block_in_human_mode_skips_the_resolver`

### refine
- sig: `refine(flow: Dev, role: str, *, review_notes: str, operator_context: str = "", worklist: str, power: str = "high") -> PlanResult`
- does: selects the prompt associated with the requested repair or replan role
- does: supplies the story, plan, findings, operator answer, and workspace directories to the turn
- does: resumes the conversation keyed to the supplied worklist
- returns: the replacement `PlanResult` from the repair turn
- verify: count(subject="development plan refinement turns", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::refine`
- tests: `workflows/tests/coder/dev/test_an_unresolvable_service_path_reworks_the_plan`

### plan_arg
- sig: `plan_arg(result: PlanResult) -> dict`
- does: projects only the structural plan fields needed by later states
- returns: services, implementation order, shared packages, verification setup, and fixtures
- verify: count(subject="development plan projections", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::plan_arg`
- tests: `workflows/tests/coder/dev/test_the_projection_carries_the_fixtures_under_either_spelling`

### implement_layer
- sig: `implement_layer(flow: Dev, operator_context: str) -> ImplResult`
- does: resolves the current layer from the recorded dispatch output
- does: resolves the layer's declared service gates before the implementation turn
- does: runs one high-power implementation prompt with the layer plan, verification setup, QA run plan, gates, and operator context
- returns: the implementation turn's structured result, including a blocked result that must be gated
- verify: count(subject="development implementation turns", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::implement_layer`
- tests: `workflows/tests/coder/dev/test_the_implement_turn_is_handed_the_two_values_its_prompt_reads`
