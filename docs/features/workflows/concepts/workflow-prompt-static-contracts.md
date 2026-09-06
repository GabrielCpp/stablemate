---
type: concept
slug: workflow-prompt-static-contracts
title: Workflow prompt static contracts
---
# Workflow prompt static contracts

The shared static checks inspect every literal `self.agent(...)` call in the author, coder,
OKF-builder, and research packages. For the coder package this means recursively walking every
Python module under `workhorse_workflows/coder`, including the main machine, every registered
sub-flow, nested QA nodes, and operator gates, rather than only traversing the flow reachable from
the default entry point. A sweep must find at least one applicable turn in every workflow;
otherwise the checker treats a changed call shape or broken walker as a failure instead of passing
vacuously.

The prompt-file check resolves each call's first positional `prompt` argument or named `prompt`
keyword. A conditional expression is expanded into all literal arms. A role envelope produced by
`roles.turn(self, "<role>")` is resolved to the calling flow's `<flow>/prompts/<role>.md` path,
using the nearest preceding literal role assignment. This preserves the coder convention that
sub-flow prompt paths are rooted at `coder/` while the prompt file remains beside the flow that
renders it. An unresolved, computed, or f-string prompt is rejected. Every resulting path must be
a file in the packaged workflow directory.

The variable check parses each literal prompt with Jinja's parser and also recognizes literal
arguments to `workhorse_var`. It compares those references with the union of argument keys passed
by all turns rendering that prompt, plus the ambient template, repository, variable, and timeout
names. It understands literal dictionaries, locally assembled dictionaries, single helper calls,
and imported package helpers whose returns are dictionary literals, including the coder shared
operator-gate argument helper. An argument expression it cannot resolve is itself rejected, so the
comparison never reports a misleading partial vocabulary. References inside Jinja raw blocks are
not counted. Per-prompt unioning is deliberate: conditional prompt sections may be supplied by
different callers.

The output-shape check resolves each literal `returns=` expression in the importing module and
reads the returned model's top-level `model_fields`. For model-returning turns, at least one fenced
JSON example must have exactly that key set, unless the prompt uses `{{ result_schema }}`, which is
rendered from the declared model at runtime. Scalar turns without a model are not shape-checked.
The comparison is top-level only; nested fields do not become envelope keys. This prevents a
reply from entering the retry/compact/reframe ladder and then defaulting to null fields because its
prompt described an unparsable shape. This prevents a coder reply from entering its retry ladder
with a wrapper or missing top-level field and then taking a default branch after parsing fails.

The OKF-builder package contributes five model-returning turns to this contract. `OkfBuilder`
enumerates entry surfaces with `Discovery`, investigates one worklist item with `Investigation`,
adjudicates one blocked finding with `Adjudication`, and adjudicates the computed uncovered list
with `Recheck`. Its web walkthrough flow drives one journey or screen with `WalkTurn`. The
investigation call has two literal prompt arms: `main/prompts/investigate.md` for discovery items
and `main/prompts/repair.md` for `fix:<doctor-code>` items. The static sweep checks both arms, while
the runtime chooses one from the item kind. Every turn passes a literal or statically resolvable
argument dictionary, including service paths and turn-specific evidence; unresolved argument
construction is a finding rather than a partial variable vocabulary.

The research package contributes eleven model-returning turns from the `Research` workflow. The
sweep includes the private recording helper as well as every public state method, because a helper
that renders a prompt is still a packaged agent turn whose path, variables, and output shape must
remain statically checkable. The shared argument reader understands `Research._program_args(...)`
and unions the program context keys with each call's turn-specific keys. The research prompts are
all rooted at `research/prompts/`, and the output-shape check resolves each declared schema from
the importing `workflow.py` module.

The package-specific call sites are:

- `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.enumerate_surfaces` →
  `main/prompts/enumerate-surfaces.md`, `Discovery`
- `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.investigate` → the two
  investigation/repair prompts, `Investigation`
- `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.adjudicate` →
  `main/prompts/adjudicate.md`, `Adjudication`
- `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.recheck` →
  `main/prompts/recheck-coverage.md`, `Recheck`
- `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.walk` →
  `walkthrough_web/prompts/walkthrough-web.md`, `WalkTurn`

The research call sites are:

- `workflows/src/workhorse_workflows/research/workflow.py::Research._record` →
  `research/prompts/record-result.md`, `RecordResult`
- `workflows/src/workhorse_workflows/research/workflow.py::Research.start` →
  `research/prompts/select-next-gate.md`, `GateSelection`
- `workflows/src/workhorse_workflows/research/workflow.py::Research.design` →
  `research/prompts/design-experiment.md`, `Design`
- `workflows/src/workhorse_workflows/research/workflow.py::Research.build` →
  `research/prompts/build-experiment.md`, `Build`
- `workflows/src/workhorse_workflows/research/workflow.py::Research.triage` →
  `research/prompts/triage-overrun.md`, `TriageResult`
- `workflows/src/workhorse_workflows/research/workflow.py::Research.check` →
  `research/prompts/gate-check.md`, `GateCheck`
- `workflows/src/workhorse_workflows/research/workflow.py::Research.lead_review` →
  `research/prompts/research-lead-review.md`, `LeadReview`
- `workflows/src/workhorse_workflows/research/workflow.py::Research.revive` →
  `research/prompts/revive-gate.md`, `ReviveResult`
- `workflows/src/workhorse_workflows/research/workflow.py::Research.new_direction` →
  `research/prompts/define-new-direction.md`, `NewDirectionResult`
- `workflows/src/workhorse_workflows/research/workflow.py::Research.goal_review` →
  `research/prompts/lead-goal-review.md`, `GoalReview`
- `workflows/src/workhorse_workflows/research/workflow.py::Research.extend` →
  `research/prompts/extend-program.md`, `ExtendResult`

The research prompt inventory and each prompt's persona contract are documented in [research
prompt contracts](research-prompt-contracts.md). This static node records the executable
alignment rule: every listed call must resolve to its packaged prompt, pass only names that the
template can read, and carry a JSON example whose top-level keys exactly match its declared reply
model. The corresponding sweep and shape checks are:

- `workflows/tests/test_prompts_exist.py::_agent_prompts`
- `workflows/tests/test_prompt_variables.py::_turns`
- `workflows/tests/test_prompt_variables.py::_keys_of_helper`
- `workflows/tests/test_prompt_variables.py::test_the_prompt_reads_only_names_the_workflow_can_supply`
- `workflows/tests/test_prompt_output_shape.py::_turns`
- `workflows/tests/test_prompt_output_shape.py::_model_fields`
- `workflows/tests/test_prompt_output_shape.py::test_the_prompt_documents_the_keys_the_turn_is_asked_for`

`{{ result_schema }}` is generated from the declared result model and is therefore exempt from
the hand-written-example comparison. Prompt variables inside a Jinja raw block are likewise not
render-time references. Any turn arguments the static reader cannot resolve fail separately,
rather than silently weakening the variable check. The same rule applies to the prompt-path
resolver: a turn that cannot be reduced to a packaged literal is a finding, not an uncovered
exception.

- code: `workflows/tests/test_prompts_exist.py::_agent_prompts`
- code: `workflows/tests/test_prompts_exist.py::_literalize`
- code: `workflows/tests/test_prompts_exist.py::_roles_by_line`
- code: `workflows/tests/test_prompt_variables.py::_turns`
- code: `workflows/tests/test_prompt_variables.py::_keys_of_local`
- code: `workflows/tests/test_prompt_variables.py::_keys_of_helper`
- code: `workflows/tests/test_prompt_variables.py::_referenced`
- code: `workflows/tests/test_prompt_output_shape.py::_model_fields`
- code: `workflows/tests/test_prompt_output_shape.py::_turns`
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.enumerate_surfaces`
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.investigate`
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.adjudicate`
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.recheck`
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.walk`
- code: `workflows/tests/test_prompts_exist.py::test_the_prompt_file_is_there`
- code: `workflows/tests/test_prompt_variables.py::test_the_prompt_reads_only_names_the_workflow_can_supply`
- code: `workflows/tests/test_prompt_output_shape.py::test_the_prompt_documents_the_keys_the_turn_is_asked_for`
- tests: `workflows/tests/test_prompts_exist.py::test_the_sweep_found_turns_in_every_workflow`
- tests: `workflows/tests/test_prompt_variables.py::test_no_turn_is_unreadable`
- tests: `workflows/tests/test_prompt_output_shape.py::test_the_sweep_found_turns_in_every_workflow`
