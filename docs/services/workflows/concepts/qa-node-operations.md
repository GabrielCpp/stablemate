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
[coder QA flow](../flows/coder-qa.md). It also names the stack copy a run holds, and releases that
copy when the run settles. The stack, release and run steps are thin nodes over the shared QA runner in
`kit/qa/runner.py`. The secret helper is private but is documented because it controls the runner's
credential boundary.

- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::__all__` @ed24680b5d25
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
- code: `workflows/src/workhorse_workflows/kit/qa/runner.py::RUN_STATUSES` @0279aa05112f

### TEARDOWN_STATES
- type: `dict[str, Literal["yes", "no", "skipped"]]`
- default: `yes -> yes, no -> no, skipped -> skipped`
- required: true
- semantics: closed mapping used to preserve whether stack teardown succeeded, failed, or was not declared
- verify: count(subject="accepted QA teardown states", equals=3)
- code: `workflows/src/workhorse_workflows/coder/shared/stack.py::TEARDOWN_STATES` @deff3c42f55a

### SECRET_MINT_TIMEOUT_S
- type: `float`
- default: `60.0`
- required: true
- semantics: maximum time allowed for one runbook secret-mint recipe before the QA run is blocked
- verify: json_path(path="$.SECRET_MINT_TIMEOUT_S", equals=60.0)
- code: `workflows/src/workhorse_workflows/kit/qa/runner.py::SECRET_MINT_TIMEOUT_S` @0279aa05112f

### QA_SCRATCH_DIRNAME
- type: `str`
- default: `qa`
- required: true
- semantics: spec-relative directory containing per-scenario dry-run output, removed with stale scored evidence and never read by the scored evidence gate
- verify: json_path(path="$.QA_SCRATCH_DIRNAME", equals="qa")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::QA_SCRATCH_DIRNAME` @ed24680b5d25

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
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::clear_qa_evidence` @ed24680b5d25

### stack_target
- sig: `stack_target(logger: logging.Logger, story: str = "", lease: str = "", repo_dir: str = "") -> StackTarget`
- does: loads the documentation graph and finds the one feature book the story's cited screens sit in
- verify: count(subject="QA stack target book lookups", equals=1)
- does: leaves `near` empty when the story is empty or cites screens in more than one book
- verify: json_path(path="$.near", equals="")
- does: resolves the environment a command run against that stack finds, keyed by the lease
- verify: json_path(path="$.env", equals="{}")
- returns: a `StackTarget` holding the book, the lease and the environment variables the stack selects
- verify: json_path(path="$.lease", equals="story-user-login-run-1")
- code: `workflows/src/workhorse_workflows/coder/shared/stack.py::stack_target` @deff3c42f55a

### ensure_stack
- sig: `ensure_stack(logger: logging.Logger, repo_dir: str = "", near: str = "", lease: str = "") -> StackStatus`
- does: resolves the docs root and loads the book's graph
- verify: count(subject="QA docs root resolutions", equals=1)
- does: returns `ready="unneeded"` when the book serves no screen or server surface and therefore needs no stack
- verify: json_path(path="$.ready", equals="unneeded")
- does: returns `ready="none"` when the book serves a screen or server but declares no stack runbook, or when several stack runbooks across environments leave bring-up with nothing to choose
- verify: json_path(path="$.ready", equals="none")
- does: brings up the run's own copy of the stack when the lease names one, and reports its entry URL
- verify: count(subject="QA stack copy bring-ups", equals=1)
- does: asks the declared stack lifecycle to adopt or bring up the stack when a manifest exists
- verify: count(subject="QA stack lifecycle ensures", equals=1)
- does: returns `ready="yes"` with process identifiers and entry URL when the stack is healthy, distinguishing adoption from a fresh bring-up in its notes
- verify: json_path(path="$.ready", equals="yes")
- does: returns `ready="no"` with the failed step and lifecycle error when stack bring-up fails
- verify: json_path(path="$.ready", equals="no")
- does: returns `ready="no"` when the stack came up but the address book it left lacks an address the environment page names
- verify: count(subject="QA stack address book problems", equals=1)
- returns: a `StackStatus` containing readiness, process identifiers, entry URL, failed step, the process groups it owns, application logs and repair notes
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/coder/shared/stack.py::ensure_stack` @deff3c42f55a
- tests: `workflows/tests/coder/qa/test_flow.py::test_an_empty_manifest_splits_on_whether_the_book_serves_anything`

### release_copy
- sig: `release_copy(logger: logging.Logger, repo_dir: str = "", near: str = "", lease: str = "") -> StackTornDown`
- does: tears down the copy of a per-run stack that the lease holds, so the next pass builds the code it QAs
- verify: json_path(path="$.torn_down", matches="^(yes|no)$")
- does: returns `torn_down="skipped"` and leaves the stack serving when the stack is shared
- verify: json_path(path="$.torn_down", equals="skipped")
- returns: a `StackTornDown` recording the teardown state and the lifecycle message
- verify: json_path(path="$.notes", equals="The stack is shared, so it stays serving.")
- code: `workflows/src/workhorse_workflows/coder/shared/stack.py::release_copy` @deff3c42f55a

### lint_qa_plan
- sig: `lint_qa_plan(logger: logging.Logger, spec_dir: str = "", repo_dir: str = "") -> QaPlanValidation`
- does: runs Ostler QA lint against `<spec_dir>/qa_plan.py` before the plan is imported or validated
- verify: count(subject="QA plan lint executions", equals=1)
- does: maps a successful lint outcome to `status="passed"` and any lint refusal to `status="invalid"`, preserving Ostler data and notes
- verify: json_path(path="$.status", equals="passed")
- returns: a `QaPlanValidation` carrying the two-state lint status, explanatory notes, and Ostler payload
- verify: json_path(path="$.ostler", absent=true)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::lint_qa_plan` @ed24680b5d25

### qa_tools_catalog
- sig: `qa_tools_catalog(logger: logging.Logger, repo_dir: str = "") -> QaToolCatalog`
- does: resolves the docs root and asks Ostler for the QA tools configured by the repository and available on the current host
- verify: count(subject="QA tool catalog resolutions", equals=1)
- returns: a `QaToolCatalog` containing the resolved tool records and any catalog errors, suitable for checkpointing across resume
- verify: json_path(path="$.tools", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::qa_tools_catalog` @ed24680b5d25

### validate_qa_plan
- sig: `validate_qa_plan(logger: logging.Logger, spec_dir: str = "", repo_dir: str = "") -> QaPlanValidation`
- does: runs Ostler QA validation against `<spec_dir>/qa_plan.py`, including importability and binding each claimed obligation to its declared verification check
- verify: count(subject="QA plan validation executions", equals=1)
- does: maps a valid outcome to `status="passed"` and any validation refusal to `status="invalid"`, preserving Ostler data and notes
- verify: json_path(path="$.status", equals="passed")
- returns: a `QaPlanValidation` carrying validation status, explanatory notes, and Ostler payload
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::validate_qa_plan` @ed24680b5d25

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
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::verify_qa_dry_run` @ed24680b5d25
- tests: `workflows/tests/coder/qa/test_dry_run_gate.py::test_a_green_dry_run_for_every_named_scenario_passes`

### teardown_stack
- sig: `teardown_stack(logger: logging.Logger, repo_dir: str = "") -> StackTornDown`
- does: tears down this run's `stack.yml` copy bring-up when one was started, and falls back to the runbook's `stop:` recipe only when there was none
- verify: count(subject="QA stack teardown attempts", equals=1)
- does: maps the lifecycle outcome to `yes`, `no`, or `skipped` and never turns cleanup failure into a failed QA verdict
- verify: json_path(path="$.torn_down", matches="^(yes|no|skipped)$")
- returns: a `StackTornDown` recording teardown state and the lifecycle message
- verify: json_path(path="$.notes", matches="^(stack torn down|teardown failed|the book declares no runbook.*|no `stop:` recipe.*)$")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/qa.py::teardown_stack` @ed24680b5d25

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
- code: `workflows/src/workhorse_workflows/kit/qa/runner.py::_mint_qa_secrets` @0279aa05112f

### run_qa_plan
- sig: `run_qa_plan(logger: logging.Logger, spec_dir: str = "", repo_dir: str = "", near: str = "", lease: str = "", only: list[str] | None = None) -> QaPlanRun`
- does: scopes plan execution to the named checks in `only` when supplied, forwarding it through to Ostler's QA run, and runs the whole plan when `only` is `None`
- verify: count(subject="scoped QA plan runs", equals=1)
- does: resolves the docs root from the supplied documentation or repository path
- verify: count(subject="resolved QA docs roots", equals=1)
- does: resolves the QA plan path from the supplied specification directory
- verify: count(subject="resolved QA plan paths", equals=1)
- does: loads the secrets of every selected stack runbook into one namespace before executing the QA plan
- verify: count(subject="loaded QA runbook secret manifests", equals=1)
- does: blocks before running the plan when two stacks declare one secret name with different mint recipes
- verify: json_path(path="$.notes", matches="declares secret .* twice")
- does: blocks before running the plan when secret minting fails
- verify: json_path(path="$.notes", matches="^QA secret refresh failed")
- does: scopes the lease's stack environment and the freshly minted secret values to the in-process Ostler QA run and removes or restores them when that run exits
- verify: removed(subject="freshly minted QA secret environment variables")
- does: invokes Ostler QA run once and ignores its process return code because the payload status is authoritative
- verify: count(subject="Ostler QA plan runs", equals=1)
- does: maps each recognized runner status (`passed`, `failed`, or `blocked`) to the identical `QaPlanRun` status
- verify: json_path(path="$.status", matches="^(passed|failed|blocked)$")
- does: maps any unrecognized runner status to `invalid`
- verify: json_path(path="$.status", equals="invalid")
- returns: a `QaPlanRun` with the runner status normalized to `passed`, `failed`, `blocked`, or `invalid` when the runner executes
- verify: json_path(path="$.status", matches="^(passed|failed|blocked|invalid)$")
- returns: a `QaPlanRun` with notes derived from the runner outcome when the runner executes
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- returns: a `QaPlanRun` carrying the Ostler payload when the runner executes
- verify: json_path(path="$.ostler.runId", equals="example runId")
- returns: a blocked `QaPlanRun` with secret-refresh notes when minting fails before runner execution
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/stack.py::run_qa_plan` @deff3c42f55a
