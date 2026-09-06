---
type: concept
slug: coder-shared-dev
title: Coder shared development helpers
---
# Coder shared development helpers

- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::__all__`
- detail: [coder development flow](../flows/coder-dev.md)
- detail: [coder resolver decision handling](coder-shared-resolution.md)

The shared development module is the deterministic boundary between a story plan and the Coder
development flow. It projects a checkpointed plan into `plan-context.json`, resolves dispatch and
QA context, moves affected repositories to the story branch, selects layers in implementation
order, discovers service-owned gate commands, executes those gates, reports story-owned changes,
and consumes operator answers. It does not decide implementation content; it returns typed values
that the flow routes.

## Fields

### MAX_GATE_OUTPUT
- type: `int`
- default: `4000`
- required: true
- semantics: failed gate output is retained from its final 4000 characters, prefixed as truncated when longer
- verify: count(subject="gate output limit", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::MAX_GATE_OUTPUT`

### GATE_TIMEOUT
- type: `int`
- default: `600`
- required: true
- semantics: a declared gate command is allowed 600 seconds before it is reported dirty for timeout
- verify: count(subject="gate timeout", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::GATE_TIMEOUT`

### GATE_ORDER
- type: `tuple[str, str]`
- default: `lint | test`
- required: true
- semantics: declared development gates are resolved and run in lint-then-test order
- verify: count(subject="development gate order", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::GATE_ORDER`

### AWAITING
- type: `str`
- default: `AWAITING_OPERATOR`
- required: true
- semantics: marks an operator context that is waiting for an answer
- verify: count(subject="awaiting operator status", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::AWAITING`

### ANSWERED
- type: `str`
- default: `ANSWERED`
- required: true
- semantics: marks an operator context containing an answer ready for consumption
- verify: count(subject="answered operator status", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::ANSWERED`

### CONSUMED
- type: `str`
- default: `CONSUMED`
- required: true
- semantics: marks an operator answer already consumed so a later block can re-arm the context
- verify: count(subject="consumed operator status", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::CONSUMED`

## Methods

### plan_document
- sig: `plan_document(plan: dict[str, Any], repos: dict[str, dict], spec_abs: Path | None = None, root: Path | None = None) -> dict[str, Any]`
- does: canonicalizes planned repository names case-insensitively against workspace keys
- does: normalizes plan files that resolve inside the story spec directory to spec-relative paths
- returns: services, implementation order, shared packages, verification setup, and typed fixture projections
- verify: count(subject="development plan documents", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::plan_document`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_projection_carries_the_fixtures_under_either_spelling`

### record_plan
- sig: `record_plan(logger: logging.Logger, plan: dict[str, Any] | None = None, spec_dir: str = "", repo_dir: str = "", workspace_file: str = "") -> PlanValidation`
- does: writes the projected plan as `plan-context.json` under the resolved spec directory
- does: rejects an empty spec directory without writing a plan projection
- does: checks every dispatched plan file is a readable file
- does: validates declared service paths and workspace markers for existing services
- does: permits a service-less plan as a repository-root dispatch when its dispatched files are valid
- returns: `valid` with the projected document, or `invalid` with deterministic errors
- verify: persists(subject="the plan-context projection")
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::record_plan`
- tests: `workflows/tests/coder/dev/test_flow.py::test_an_unresolvable_service_path_reworks_the_plan`

### read_plan_text
- sig: `read_plan_text(spec_dir: str, plan_file: str, logger: logging.Logger) -> str`
- does: reads the selected plan file relative to the spec directory
- raises: `OSError` when the selected plan file cannot be read
- returns: the plan file's UTF-8 content without fallback text
- verify: count(subject="inlined implementation plan", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::read_plan_text`

### resolve_impl_context
- sig: `resolve_impl_context(logger: logging.Logger, spec_dir: str = "", target_env: str = "local", docs_path: str = "", repo_dir: str = "", workspace_file: str = "", plan: dict[str, Any] | None = None) -> ImplContext`
- does: uses the checkpointed plan when present and otherwise loads the plan projection from disk
- does: creates a repository-root fallback dispatch when the plan is absent or names no services
- does: excludes Terraform and documentation layers from the QA run plan
- does: excludes QA skills ending in `-local` when the target environment is not local
- does: includes the documentation root in affected repository paths when it is not already affected
- does: creates one unique `surface=source-root` QA source-root entry for each dispatched surface
- returns: dispatch, QA, fixture, shared-package, affected-repository, and source-root context
- verify: count(subject="resolved implementation contexts", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::resolve_impl_context`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_implement_turn_is_handed_the_two_values_its_prompt_reads`

### plan_summary
- sig: `plan_summary(logger: logging.Logger, spec_dir: str = "", repo_dir: str = "", workspace_file: str = "") -> PlanSummary`
- does: renders each planned service with its type and plan file
- does: renders implementation order, shared packages, verification setup, named fixtures, and unnamed arrangements when present
- returns: blank text when the projection is missing or declares no services, otherwise a human-readable plan summary
- verify: count(subject="rendered plan summaries", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::plan_summary`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_summary_says_the_names_apart_from_the_arrangements`

### branch_code_repos
- sig: `branch_code_repos(logger: logging.Logger, spec_dir: str = "", branch: str = "", docs_path: str = "", repo_dir: str = "", workspace_file: str = "", plan: dict[str, Any] | None = None) -> BranchOutcome`
- does: derives the affected repositories from the plan
- does: uses the documentation repository branch when no branch is supplied, or `main` when that root is not a git repository
- does: creates or checks out the requested branch in each affected code repository
- does: leaves repositories already on the requested branch unchanged and skips non-git repositories
- returns: names of repositories branched and already on the branch
- verify: count(subject="story branch dispatch", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::branch_code_repos`
- tests: `workflows/tests/coder/dev/test_flow.py::test_plans_stamps_branches_and_implements_every_layer`

### select_next_layer
- sig: `select_next_layer(logger: logging.Logger, spec_dir: str = "", index: int = -1, repo_dir: str = "", workspace_file: str = "", plan: dict[str, Any] | None = None) -> LayerPick`
- does: selects the dispatch entry immediately after the supplied completed-layer index
- does: applies repository-root fallback for a producing plan with no services or an absent projection
- returns: the next layer with its index and dispatch count, or the unchanged index with `has_layer=false` when exhausted
- verify: count(subject="next development layer selections", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::select_next_layer`

### service_keys
- sig: `service_keys(service: str = "", service_type: str = "") -> list[str]`
- does: derives lookup keys from the complete dispatch id, its path, the path basename, and the service type
- returns: unique non-empty keys in narrowest-first order
- verify: count(subject="service declaration lookup keys", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::service_keys`
- tests: `workflows/tests/coder/shared/test_gates.py::test_the_dispatch_id_is_decomposed_into_the_keys_a_repo_actually_writes`

### service_declaration
- sig: `service_declaration(service: str = "", service_type: str = "", repo_dir: str = "") -> dict`
- does: loads the orchestrating repository's service declarations
- does: returns the first dictionary found by service, path, basename, then service type
- returns: the selected gate declaration or an empty mapping
- verify: count(subject="service declaration selection", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::service_declaration`
- tests: `workflows/tests/coder/shared/test_gates.py::test_a_service_name_beats_its_type`

### service_dir
- sig: `service_dir(cwd: str | Path, service: str = "") -> Path`
- does: resolves a nested dispatch service path beneath the repository checkout
- does: falls back to the supplied checkout for a root service, a missing path, or a non-directory
- returns: the directory in which that service's gate command runs
- verify: count(subject="service gate working directories", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::service_dir`
- tests: `workflows/tests/coder/shared/test_gates.py::test_a_services_gate_runs_in_the_service_directory_not_the_repo_root`

### gate_command
- sig: `gate_command(gate: str, service: str, service_type: str, cwd: Path, repo_dir: str = "") -> str`
- does: selects a non-empty gate command from the service declaration before legacy lint configuration
- does: uses the legacy lint map only for lint when no service declaration supplies it
- does: falls back to `make <gate>` only when the service Makefile defines that target
- returns: the selected command or an empty string when the gate is not adopted
- verify: count(subject="resolved service gate commands", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::gate_command`
- tests: `workflows/tests/coder/shared/test_gates.py::test_a_makefile_target_is_the_last_resort`

### declared_gates
- sig: `declared_gates(logger: logging.Logger, cwd: str = "", service: str = "", service_type: str = "", repo_dir: str = "") -> GateList`
- does: resolves commands for every gate in `GATE_ORDER` at the service directory
- does: reports `(nothing declared)` when no gate is adopted
- returns: gate names, commands, and their execution-directory annotation
- verify: count(subject="declared gate summaries", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::declared_gates`
- tests: `workflows/tests/coder/shared/test_gates.py::test_declared_gates_renders_the_commands_that_will_run`

### declared_markers
- sig: `declared_markers(logger: logging.Logger, repo_dir: str = "", workspace_file: str = "") -> GateList`
- does: reads each workspace repository's declared service marker files
- returns: one repository line per repository with markers, or blank text when none are declared
- verify: count(subject="declared service markers", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::declared_markers`
- tests: `workflows/tests/coder/shared/test_gates.py::test_the_planner_is_told_the_markers_this_workspace_declares`

### run_gate
- sig: `run_gate(logger: logging.Logger, cwd: str = "", service: str = "", gate: str = "lint", service_type: str = "", repo_dir: str = "") -> GateOutcome`
- does: skips when no checkout directory or adopted command exists
- does: runs the adopted command in the resolved service directory with the configured timeout
- does: returns `clean` only for exit code zero
- does: returns `dirty` for a non-zero exit, timeout, or truncated combined output
- returns: the gate name, status, command, output, and reason
- verify: count(subject="executed development gates", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::run_gate`
- tests: `workflows/tests/coder/shared/test_gates.py::test_a_failing_command_is_dirty_and_carries_its_output`

### check_story_status
- sig: `check_story_status(logger: logging.Logger, docs_path: str = "", slug: str = "", epic: str = "", story_path: str = "", repo_dir: str = "") -> StoryStatusCheck`
- does: reads the story status through the shared status adapter
- does: reports `dirty` when the status marks the story finished before QA
- returns: `clean` with the written status when it is not finished, otherwise `dirty` with that status
- verify: count(subject="pre-QA story status checks", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::check_story_status`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_turn_that_stamps_the_story_finished_is_sent_back`

### changed_files
- sig: `changed_files(logger: logging.Logger, cwd: str = "", story_slug: str = "", story_id: str = "") -> ChangedFiles`
- does: collects modified and staged paths from the checkout
- does: includes non-ignored untracked paths
- does: includes paths from commits matching the exact story id or slug trailer
- returns: sorted unique changed paths and an empty result for an unusable checkout or failed git query
- verify: count(subject="story changed-file reports", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::changed_files`
- tests: `workflows/tests/coder/shared/test_gates.py::test_a_new_file_is_in_the_diff_the_gates_read`

### resolve_story_sources
- sig: `resolve_story_sources(logger: logging.Logger, dispatch: tuple[DispatchEntry, ...], story_slug: str = "", story_id: str = "", docs_path: str = "", repo_dir: str = "") -> StorySources`
- does: resolves one base commit per implementation repository from the earliest exact story trailer
- does: deduplicates repeated repository, surface, and service-root entries
- returns: valid story source provenance, or invalid errors for missing story identity, missing source repositories, conflicting checkouts, or absent story commits
- verify: count(subject="story source provenance", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::resolve_story_sources`

### read_operator_context
- sig: `read_operator_context(logger: logging.Logger, story_path: str = "") -> OperatorAnswer`
- does: reads the operator context adjacent to the story when it exists
- does: changes `STATUS: ANSWERED` to `STATUS: CONSUMED` after taking the answer
- does: treats only `SCOPE: epic` as epic scope and narrows every other value to story scope
- returns: unanswered when the context file is absent, otherwise answered with scope and original content
- verify: persists(subject="consumed operator answer status")
- code: `workflows/src/workhorse_workflows/coder/shared/dev.py::read_operator_context`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_resolver_that_grounds_its_answer_settles_the_block_without_a_person`
