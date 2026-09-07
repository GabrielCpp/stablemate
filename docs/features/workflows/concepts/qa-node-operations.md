---
type: concept
slug: qa-node-operations
title: QA node operations
---
# QA node operations

The QA node module is the deterministic boundary around planning and executing one story's QA
plan. It clears stale evidence, resolves and manages the durable stack, lints and validates the
plan, catalogs host-resolved tools, proves repaired scenarios with isolated dry-run evidence, and
normalizes the runner and teardown outcomes into the typed results consumed by the
[coder QA flow](../flows/coder-qa.md). The secret helper is private but is documented because it
controls the runner's credential boundary.

- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::__all__`
- detail: [coder QA flow](../flows/coder-qa.md)

## Fields

### RUN_STATUSES
- type: `dict[str, QaStatus]`
- default: `passed -> passed, failed -> failed, blocked -> blocked, invalid -> invalid`
- required: true
- semantics: closed mapping from the Ostler runner's status text to the four statuses accepted by `QaPlanRun`
- verify: count(subject="accepted QA runner statuses", equals=4)
- semantics: any other runner status text becomes `invalid`
- verify: json_path(path="$.status", equals="invalid")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::RUN_STATUSES`

### TEARDOWN_STATES
- type: `dict[str, Literal["yes", "no", "skipped"]]`
- default: `yes -> yes, no -> no, skipped -> skipped`
- required: true
- semantics: closed mapping used to preserve whether stack teardown succeeded, failed, or was not declared
- verify: count(subject="accepted QA teardown states", equals=3)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::TEARDOWN_STATES`

### SECRET_MINT_TIMEOUT_S
- type: `float`
- default: `60.0`
- required: true
- semantics: maximum time allowed for one runbook secret-mint recipe before the QA run is blocked
- verify: json_path(path="$.SECRET_MINT_TIMEOUT_S", equals=60.0)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::SECRET_MINT_TIMEOUT_S`

### QA_SCRATCH_DIRNAME
- type: `str`
- default: `qa`
- required: true
- semantics: spec-relative directory containing per-scenario dry-run output, removed with stale scored evidence and never read by the scored evidence gate
- verify: json_path(path="$.QA_SCRATCH_DIRNAME", equals="qa")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::QA_SCRATCH_DIRNAME`

## Methods

### clear_qa_evidence
- sig: `clear_qa_evidence(logger: logging.Logger, spec_dir: str = "") -> QaCleared`
- does: returns an un-cleared result and leaves the filesystem unchanged when `spec_dir` is empty
- verify: count(subject="empty QA evidence directory skips", equals=1)
- does: creates the resolved specification directory when a non-empty `spec_dir` is supplied
- verify: created(subject="QA specification directory")
- does: removes the specification directory's `qa/` subtree when it exists, including dry-run scratch output
- verify: removed(subject="stale QA evidence directory")
- does: removes `qa-evidence.json` and `qa-report.md` when either stale root artifact exists
- verify: removed(subject="stale QA root artifacts")
- returns: `QaCleared(cleared=True)` after clearing a supplied specification directory and `QaCleared(cleared=False)` when no directory was supplied
- verify: json_path(path="$.cleared", equals=true)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::clear_qa_evidence`
- tests: `workflows/tests/coder/qa/test_flow.py::test_one_clean_pass_through_every_gate`

### ensure_stack
- sig: `ensure_stack(logger: logging.Logger, docs_path: str = "", repo_dir: str = "") -> StackStatus`
- does: resolves the docs root
- verify: count(subject="QA docs root resolutions", equals=1)
- does: loads the book's stack manifest
- verify: count(subject="QA stack manifest loads", equals=1)
- does: returns `ready="unneeded"` when the book serves no screen or server surface and therefore needs no stack
- verify: json_path(path="$.ready", equals="unneeded")
- does: returns `ready="none"` when the book serves a screen or server but declares no stack runbook or walkthrough server
- verify: json_path(path="$.ready", equals="none")
- does: asks the declared stack lifecycle to adopt or bring up the stack when a manifest exists
- verify: count(subject="QA stack lifecycle ensures", equals=1)
- does: returns `ready="yes"` with process identifiers and entry URL when the stack is healthy, distinguishing adoption from a fresh bring-up in its notes
- verify: json_path(path="$.ready", equals="yes")
- does: returns `ready="no"` with the failed step and lifecycle error when stack bring-up fails
- verify: json_path(path="$.ready", equals="no")
- returns: a `StackStatus` containing readiness, process identifiers, entry URL, failed step, and repair notes
- verify: json_path(path="$.notes", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::ensure_stack`
- tests: `workflows/tests/coder/qa/test_flow.py::test_an_empty_manifest_splits_on_whether_the_book_serves_anything`

### lint_qa_plan
- sig: `lint_qa_plan(logger: logging.Logger, spec_dir: str = "", docs_path: str = "", repo_dir: str = "") -> QaPlanValidation`
- does: runs Ostler QA lint against `<spec_dir>/qa_plan.py` before the plan is imported or validated
- verify: count(subject="QA plan lint executions", equals=1)
- does: maps a successful lint outcome to `status="passed"` and any lint refusal to `status="invalid"`, preserving Ostler data and notes
- verify: json_path(path="$.status", equals="passed")
- returns: a `QaPlanValidation` carrying the two-state lint status, explanatory notes, and Ostler payload
- verify: json_path(path="$.ostler", absent=true)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::lint_qa_plan`

### qa_tools_catalog
- sig: `qa_tools_catalog(logger: logging.Logger, docs_path: str = "", repo_dir: str = "") -> QaToolCatalog`
- does: resolves the docs root and asks Ostler for the QA tools configured by the repository and available on the current host
- verify: count(subject="QA tool catalog resolutions", equals=1)
- returns: a `QaToolCatalog` containing the resolved tool records and any catalog errors, suitable for checkpointing across resume
- verify: json_path(path="$.tools", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::qa_tools_catalog`

### validate_qa_plan
- sig: `validate_qa_plan(logger: logging.Logger, spec_dir: str = "", docs_path: str = "", repo_dir: str = "") -> QaPlanValidation`
- does: runs Ostler QA validation against `<spec_dir>/qa_plan.py`, including importability and binding each claimed obligation to its declared verification check
- verify: count(subject="QA plan validation executions", equals=1)
- does: maps a valid outcome to `status="passed"` and any validation refusal to `status="invalid"`, preserving Ostler data and notes
- verify: json_path(path="$.status", equals="passed")
- returns: a `QaPlanValidation` carrying validation status, explanatory notes, and Ostler payload
- verify: json_path(path="$.notes", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::validate_qa_plan`
- tests: `workflows/tests/coder/qa/test_flow.py::test_one_clean_pass_through_every_gate`

### verify_qa_dry_run
- sig: `verify_qa_dry_run(logger: logging.Logger, spec_dir: str = "", scenarios: tuple[str, ...] = ()) -> DryRunGate`
- does: treats an empty scenario list as an already-passed gate with no verified scenarios
- verify: json_path(path="$.status", equals="passed")
- does: reads each named scenario's `qa/<scenario>/qa-run.ndjson` scratch log and refuses a scenario whose log is absent
- verify: absent(subject="dry-run log for an unexecuted scenario")
- does: refuses a scenario whose log contains no assertion record for that scenario, allowing an unlabeled assertion only when the scenario owns the output directory
- verify: count(subject="dry-run assertion records", equals=1)
- does: refuses a scenario when any of its assertion records has result `FAIL`
- verify: count(subject="failed dry-run assertions", equals=0)
- does: marks every named scenario with assertions and no failures as verified while retaining the complete requested scenario list
- verify: count(subject="verified dry-run scenarios", equals=1)
- returns: a `DryRunGate` with `passed` or `failed` status, notes, requested scenarios, and the verified subset
- verify: json_path(path="$.status", matches="^(passed|failed)$")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::verify_qa_dry_run`
- tests: `workflows/tests/coder/qa/test_dry_run_gate.py::test_a_green_dry_run_for_every_named_scenario_passes`

### teardown_stack
- sig: `teardown_stack(logger: logging.Logger, docs_path: str = "", repo_dir: str = "") -> StackTornDown`
- does: resolves the docs root and invokes the runbook stop recipe after the QA run reaches a terminal path
- verify: count(subject="QA stack teardown attempts", equals=1)
- does: maps the lifecycle outcome to `yes`, `no`, or `skipped` and never turns cleanup failure into a failed QA verdict
- verify: json_path(path="$.torn_down", matches="^(yes|no|skipped)$")
- returns: a `StackTornDown` recording teardown state and the lifecycle message
- verify: json_path(path="$.notes", matches="^(stack torn down|teardown failed|the book declares no runbook.*|no `stop:` recipe.*)$")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::teardown_stack`

### _mint_qa_secrets
- sig: `_mint_qa_secrets(secrets: dict[str, str], root: Path, logger: logging.Logger) -> tuple[dict[str, str], str]`
- does: returns no tokens and no error when the runbook declares no secrets
- verify: count(subject="empty QA secret mint results", equals=1)
- does: runs each non-empty repository-owned recipe from the resolved repository root with a 60-second timeout and captures its trimmed stdout as that secret's value
- verify: count(subject="QA secret mint recipes", equals=1)
- does: stops at the first invalid recipe, execution error, timeout, non-zero exit, or empty output and discards every token minted earlier in that loop
- verify: count(subject="all-or-nothing QA secret mint failures", equals=1)
- returns: a complete token mapping with an empty error on success, or an empty mapping with a diagnostic error on failure
- verify: json_path(path="$.error", equals="")
- returns: token values are not logged
- verify: omits(subject="QA secret mint logs", matches="token value")
- returns: token values are not returned by a node schema
- verify: omits(subject="QA node return payload", matches="token value")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::_mint_qa_secrets`
- tests: `workflows/tests/coder/qa/test_refresh_env.py::test_an_earlier_failure_discards_the_tokens_already_minted`

### run_qa_plan
- sig: `run_qa_plan(logger: logging.Logger, spec_dir: str = "", docs_path: str = "", repo_dir: str = "") -> QaPlanRun`
- does: resolves the docs root from the supplied documentation or repository path
- verify: count(subject="resolved QA docs roots", equals=1)
- does: resolves the QA plan path from the supplied specification directory
- verify: count(subject="resolved QA plan paths", equals=1)
- does: loads the runbook secrets before executing the QA plan
- verify: count(subject="loaded QA runbook secret manifests", equals=1)
- does: blocks before running the plan when secret minting fails
- verify: json_path(path="$.status", equals="blocked")
- does: scopes freshly minted secret values to the in-process Ostler QA run and removes or restores them when that run exits
- verify: removed(subject="freshly minted QA secret environment variables")
- does: invokes Ostler QA run once and ignores its process return code because the payload status is authoritative
- verify: count(subject="Ostler QA plan runs", equals=1)
- does: maps runner statuses `passed`, `failed`, and `blocked` directly and maps any unrecognized status to `invalid`
- verify: count(subject="normalized QA plan run statuses", equals=4)
- returns: a `QaPlanRun` with normalized status, notes, and the Ostler payload when the runner executes, or a blocked result with secret-refresh notes before execution
- verify: json_path(path="$.notes", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::run_qa_plan`
- tests: `workflows/tests/coder/qa/test_flow.py::test_one_clean_pass_through_every_gate`
