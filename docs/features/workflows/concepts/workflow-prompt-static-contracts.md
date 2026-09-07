---
type: concept
slug: workflow-prompt-static-contracts
title: Workflow prompt static contracts
---
# Workflow prompt static contracts

The prompt-path sweep inspects every literal `self.agent(...)` call in the `author`, `coder`,
`hello_world`, `okf_builder`, and `research` packages. For the coder package this means recursively walking every
Python module under `workhorse_workflows/coder`, including the main machine, every registered
sub-flow, nested QA nodes, and operator gates, rather than only traversing the flow reachable from
the default entry point. A sweep must find at least one applicable turn in every workflow;
otherwise the checker treats a changed call shape or broken walker as a failure instead of passing
vacuously.

The sweep is source-based rather than runtime-based. It parses each packaged Python module,
records the workflow name, source path, line number, and prompt expression for every matching
`self.agent(...)` call, and checks the resulting collection as one parametrized set. This reaches
turns hidden behind nested sub-flows or operator gates without requiring a run to enter those
states.

The prompt-file check resolves each call's first positional `prompt` argument or named `prompt`
keyword. A conditional expression is expanded into all literal arms. A role envelope produced by
`roles.turn(self, "<role>")` is resolved to the calling flow's `<flow>/prompts/<role>.md` path,
using the nearest preceding literal role assignment. This preserves the coder convention that
sub-flow prompt paths are rooted at `coder/` while the prompt file remains beside the flow that
renders it. An unresolved, computed, or f-string prompt is rejected. Every resulting path must be
a file in the packaged workflow directory.

The resolver expands a conditional prompt recursively, so both literal arms are checked. It also
rewrites `turn.prompt` to the envelope path derived from the nearest preceding literal
`roles.turn(self, ...)` assignment in the same source walk. A role assignment with a non-string
or otherwise non-literal arm is not partially accepted. The final path is joined to the workflow
package selected by `WORKFLOWS`, and `test_the_prompt_file_is_there` rejects both non-string AST
expressions and missing files.

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

- code: `workflows/tests/test_prompts_exist.py::_agent_prompts`
- code: `workflows/tests/test_prompts_exist.py::_branches`
- code: `workflows/tests/test_prompts_exist.py::_literalize`
- code: `workflows/tests/test_prompts_exist.py::_roles_by_line`
- code: `workflows/tests/test_prompts_exist.py::_sites`
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
- tests: `workflows/tests/test_prompts_exist.py::test_the_prompt_file_is_there`
- tests: `workflows/tests/test_prompt_variables.py::test_the_prompt_reads_only_names_the_workflow_can_supply`
- tests: `workflows/tests/test_prompt_output_shape.py::test_the_prompt_documents_the_keys_the_turn_is_asked_for`
- tests: `workflows/tests/test_prompts_exist.py::test_the_sweep_found_turns_in_every_workflow`
- tests: `workflows/tests/test_prompt_variables.py::test_no_turn_is_unreadable`
- tests: `workflows/tests/test_prompt_output_shape.py::test_the_sweep_found_turns_in_every_workflow`

## Methods

The prompt-variable test module implements the variable side of this contract with a deliberately
limited AST resolver. It accepts only statically nameable argument shapes; an unreadable shape is a
finding rather than a partial vocabulary that could produce a false missing-variable report.

### _package_defs

- sig: `_package_defs() -> dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]]`
- code: `workflows/tests/test_prompt_variables.py::_package_defs`

Indexes module-level synchronous and asynchronous function definitions across the installed
workflow package. Methods are excluded so same-named methods in different lanes cannot be mistaken
for importable helpers.

### _dict_keys

- sig: `_dict_keys(node: ast.Dict, spread: str | None, scope: ast.AST, module: ast.Module) -> set[str] | None`
- code: `workflows/tests/test_prompt_variables.py::_dict_keys`

Returns literal string keys from a dictionary expression, recursively resolving supported `**`
expansions. It ignores the helper's declared `**kwargs` expansion and returns `None` when a key or
expansion cannot be named statically.

### _keys_of

- sig: `_keys_of(node: ast.expr, scope: ast.AST, module: ast.Module) -> set[str] | None`
- code: `workflows/tests/test_prompt_variables.py::_keys_of`

Dispatches static argument-key resolution for dictionary literals, local dictionary names,
instance helper calls, and imported module-level helper calls. Other expressions are unreadable.

### _keys_of_local

- sig: `_keys_of_local(name: str, scope: ast.AST, module: ast.Module) -> set[str] | None`
- code: `workflows/tests/test_prompt_variables.py::_keys_of_local`

Collects keys assigned to a local dictionary both at initialization and through literal-key
subscript assignments. A computed assignment key or unreadable value makes the result unreadable.

### _defs

- sig: `_defs(name: str, module: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]`
- code: `workflows/tests/test_prompt_variables.py::_defs`

Uses definitions in the current module when present; otherwise returns the package-wide index for
an imported helper. This local-first rule prevents an unrelated same-named helper from determining
the call site's vocabulary.

### _keys_of_helper

- sig: `_keys_of_helper(name: str, call: ast.Call, module: ast.Module) -> set[str] | None`
- code: `workflows/tests/test_prompt_variables.py::_keys_of_helper`

Resolves a helper only when exactly one definition exists and every return is a dictionary literal,
then adds the call's literal keyword names. Multiple definitions, missing returns, non-dictionary
returns, or an opaque `**` expansion are unreadable.

### _scopes

- sig: `_scopes(tree: ast.Module) -> dict[int, ast.AST]`
- code: `workflows/tests/test_prompt_variables.py::_scopes`

Maps every call node to its innermost enclosing function, so local dictionary analysis does not
merge identically named locals from separate functions.

### _turns

- sig: `_turns(source: Path) -> tuple[list[tuple[int, str, set[str]]], list[int]]`
- code: `workflows/tests/test_prompt_variables.py::_turns`

Finds every literal-prompt `self.agent(..., args=...)` call in one source file and records its line,
prompt path, and statically resolved argument names. It separately records call lines whose
arguments cannot be resolved and ignores non-literal prompt expressions because prompt-path
validation owns those findings.

### _prompts

- sig: `_prompts() -> dict[tuple[str, str], tuple[set[str], list[str]]]`
- code: `workflows/tests/test_prompt_variables.py::_prompts`

Walks every Python module in the four configured workflow packages, unions the argument vocabulary
for each `(workflow, prompt)` pair, and records all rendering call sites. The union is intentional:
conditional prompt sections may be supplied by different callers.

### _referenced

- sig: `_referenced(body: str) -> set[str]`
- code: `workflows/tests/test_prompt_variables.py::_referenced`

Parses a prompt with Jinja, returns undeclared template names, and adds literal names passed to
`workhorse_var`. References inside Jinja raw blocks are excluded by the parser.

### test_the_sweep_checks_every_workflow

- sig: `test_the_sweep_checks_every_workflow() -> None`
- code: `workflows/tests/test_prompt_variables.py::test_the_sweep_checks_every_workflow`
- tests: `workflows/tests/test_prompt_variables.py::test_the_sweep_checks_every_workflow`

Fails if the prompt-variable inventory has no prompt for any configured workflow, preventing a
walker that matches nothing from passing vacuously.

### test_no_turn_is_unreadable

- sig: `test_no_turn_is_unreadable() -> None`
- code: `workflows/tests/test_prompt_variables.py::test_no_turn_is_unreadable`
- tests: `workflows/tests/test_prompt_variables.py::test_no_turn_is_unreadable`

Fails when any literal prompt call builds its argument mapping in a shape the static resolver
cannot name, because that would make the subsequent missing-variable report incomplete.

### test_the_prompt_reads_only_names_the_workflow_can_supply

- sig: `test_the_prompt_reads_only_names_the_workflow_can_supply(workflow: str, prompt: str) -> None`
- code: `workflows/tests/test_prompt_variables.py::test_the_prompt_reads_only_names_the_workflow_can_supply`
- tests: `workflows/tests/test_prompt_variables.py::test_the_prompt_reads_only_names_the_workflow_can_supply`

For every discovered workflow/prompt pair, the test fails if Jinja or `workhorse_var` references a
name outside the prompt's unioned call-site vocabulary and the ambient names. The failure identifies
the rendering sites and supplied vocabulary so an author can repair the prompt or its caller.

`{{ result_schema }}` is generated from the declared result model and is therefore exempt from the
hand-written-example comparison. Prompt variables inside a Jinja raw block are likewise not
render-time references. Any turn arguments the static reader cannot resolve fail separately,
rather than silently weakening the variable check. The same rule applies to the prompt-path
resolver: a turn that cannot be reduced to a packaged literal is a finding, not an uncovered
exception.

The output-shape half is implemented by `test_prompt_output_shape.py`. It walks source rather than
executing the workflows, so model-returning turns in nested sub-flows remain covered even when no
runtime path reaches them. A turn without a declared model is intentionally outside this check.

### _top_level_keys

- sig: `_top_level_keys(body: str) -> set[str] | None`
- code: `workflows/tests/test_prompt_output_shape.py::_top_level_keys`

Scans the first fenced JSON object for keys at depth one without requiring valid JSON. Pseudo-JSON
such as a documented enum is accepted; no object or no readable key produces `None`.

### _turns_output_shape

The two prompt-contract modules both expose `_turns`, but they are separate source symbols. The
variable checker records argument names, while this module records model-returning calls. The
output-shape symbol accepts positional or named literal prompts, requires a literal `returns=`
expression, and records each matching call's line, prompt path, and return expression. Calls with
missing returns, non-literal prompts, or non-`self.agent` callees are excluded because another
check owns those findings or because no model shape is available.

- sig: `_turns(source: Path) -> list[tuple[int, str, ast.expr]]`
- code: `workflows/tests/test_prompt_output_shape.py::_turns`

### _sites

- sig: `_sites() -> list[tuple[str, Path, int, str, ast.expr]]`
- code: `workflows/tests/test_prompt_output_shape.py::_sites`

Enumerates Python files recursively beneath each configured workflow package and aggregates the
literal model-returning turns with their workflow name and source location. The configured set is
`author`, `coder`, `okf_builder`, and `research`; the sweep must find at least one turn in each.

### _model_fields

- sig: `_model_fields(source: Path, returns: ast.expr) -> set[str]`
- code: `workflows/tests/test_prompt_output_shape.py::_model_fields`

Imports the module containing the turn, resolves the declared return expression in that module's
namespace, and returns the model's top-level field names. This preserves caller-local name binding
and deliberately does not treat nested fields as envelope keys.

### test_the_sweep_found_turns_in_every_workflow

- sig: `test_the_sweep_found_turns_in_every_workflow() -> None`
- code: `workflows/tests/test_prompt_output_shape.py::test_the_sweep_found_turns_in_every_workflow`
- tests: `workflows/tests/test_prompt_output_shape.py::test_the_sweep_found_turns_in_every_workflow`

Rejects a source walker that finds no applicable model-returning turn for any configured workflow,
preventing the output-shape suite from passing vacuously after a call-shape or traversal change.

### test_the_prompt_documents_the_keys_the_turn_is_asked_for

- sig: `test_the_prompt_documents_the_keys_the_turn_is_asked_for(workflow: str, source: Path, lineno: int, prompt: str, returns: ast.expr) -> None`
- code: `workflows/tests/test_prompt_output_shape.py::test_the_prompt_documents_the_keys_the_turn_is_asked_for`
- tests: `workflows/tests/test_prompt_output_shape.py::test_the_prompt_documents_the_keys_the_turn_is_asked_for`

For each model-returning turn, requires a fenced JSON example whose top-level keys exactly equal
the declared model fields. Prompts containing `{{ result_schema }}` are exempt because the runtime
renders that schema from the same declared model. A mismatch identifies the source call and prompt,
so wrapped, missing, or extra keys cannot silently enter the retry ladder and default to null.
