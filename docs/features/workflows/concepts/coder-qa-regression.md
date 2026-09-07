---
type: concept
slug: coder-qa-regression
title: Coder QA regression suites
---
# Coder QA regression suites

The regression node group discovers journey suites declared by the touched services and runs
those commands without asking an agent to interpret the result. It is linked from the
[Coder QA subflow](coder-qa-subflow.md), which invokes detection before execution. The detector
fails open when the plan context cannot identify suites; the runner distinguishes no suite or no
flows (`skipped`) from an unstartable declaration (`error`), an unreachable or hung stack
(`blocked`), a non-zero suite result (`failed`), and a clean exit (`passed`). Raw combined output
is retained in the QA directory when one is supplied, and parsed failures are attributed to the
book's verification index for diagnosis only.

- code: `workflows/src/workhorse_workflows/coder/qa/nodes/regression.py::__all__`
- detail: [Coder QA subflow](coder-qa-subflow.md)

## Fields

### REGRESSION_GATE
- type: `str`
- default: `regression`
- required: true
- semantics: the service configuration key whose declared command is resolved for a journey suite
- verify: json_path(path="$.REGRESSION_GATE", equals="regression")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/regression.py::REGRESSION_GATE`

### SUITE_TIMEOUT
- type: `int`
- default: `1500`
- required: true
- semantics: the maximum seconds allowed for one declared suite command before it is classified as blocked
- verify: json_path(path="$.SUITE_TIMEOUT", equals=1500)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/regression.py::SUITE_TIMEOUT`

### STATUS_ORDER
- type: `dict[str, int]`
- default: `error -> 0, blocked -> 1, failed -> 2, passed -> 3, skipped -> 4`
- required: true
- semantics: worst-first precedence used when combining results from multiple services
- verify: count(subject="regression result statuses", equals=5)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/regression.py::STATUS_ORDER`

## Methods

### detect_regression_suites
- sig: `detect_regression_suites(logger: logging.Logger, spec_dir: str = "", repo_dir: str = "", workspace_file: str = "") -> RegressionSuites`
- does: reads `<repo-root>/<spec_dir>/plan-context.json` when `spec_dir` is supplied and treats an unreadable or absent context as an empty service list
- verify: count(subject="regression plan-context reads", equals=1)
- does: resolves each planned service in the workspace and skips services whose repository has no resolved path
- verify: count(subject="workspace-resolved regression services", equals=1)
- does: asks the shared gate-command resolver for the service's `regression` declaration and omits services with no command
- verify: count(subject="declared regression command selections", equals=1)
- returns: a `RegressionSuites` containing one `RegressionSuite` per touched service with a declared command, its `<repo path>::<service path>` label, absolute working directory, and command
- verify: count(subject="resolved regression suites", equals=1)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/regression.py::detect_regression_suites`
- tests: `workflows/tests/coder/qa/test_flow.py::test_a_failing_journey_suite_is_fixed_and_the_story_is_re_qad`

### run_regression_suite
- sig: `run_regression_suite(logger: logging.Logger, spec_dir: str = "", qa_dir: str = "", suites: list | None = None, repo_dir: str = "") -> RegressionRun`
- does: returns `status="skipped"` with a no-suite note when no resolved service declares a regression suite
- verify: json_path(path="$.status", equals="skipped")
- does: validates each supplied suite record and runs every declared command from its service working directory with the suite timeout
- verify: count(subject="declared regression suite executions", equals=1)
- does: classifies a clean command exit as `passed`
- verify: json_path(path="$.status", equals="passed")
- does: classifies a non-zero exit containing a no-tests indication as `skipped`
- verify: json_path(path="$.status", equals="skipped")
- does: classifies an unreachable or timed-out running suite as `blocked`
- verify: json_path(path="$.status", equals="blocked")
- does: classifies a missing service directory or unstartable declared command as `error`
- verify: json_path(path="$.status", equals="error")
- does: classifies other non-zero exits as `failed` and records parsed failing test paths and names, or the output tail when individual failures cannot be parsed
- verify: json_path(path="$.failing_tests[0]", matches="^.+: .+$")
- does: writes combined standard output and error to a sanitized per-service QA log when `qa_dir` is supplied, without changing the verdict if the log cannot be written
- verify: created(subject="regression suite output log")
- does: merges multiple service results by worst status precedence while retaining all failing tests, log paths, and notes
- verify: count(subject="merged regression suite results", equals=1)
- does: attributes each failed test to verification-index owners as `impacted`, `outside-impact`, or `unattributed` without changing the suite status
- verify: json_path(path="$.failure_attribution[0].classification", matches="^(impacted|outside-impact|unattributed)$")
- returns: a `RegressionRun` carrying one of `passed`, `failed`, `blocked`, `skipped`, or `error`, failure details, persisted log paths, notes, and optional verification-index attribution
- verify: json_path(path="$.notes", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/regression.py::run_regression_suite`
- tests: `workflows/tests/coder/qa/test_flow.py::test_a_journey_suite_that_stays_red_falls_into_the_qa_fix_loop`

### RegressionRun.as_qa_result
- sig: `RegressionRun.as_qa_result(self) -> QaResult`
- does: maps `skipped` to the downstream QA status `passed` while retaining the regression status in the notes
- verify: json_path(path="$.status", equals="passed")
- does: maps `error` to downstream QA status `blocked` while retaining the error classification in the notes
- verify: json_path(path="$.status", equals="blocked")
- does: preserves `passed`, `failed`, and `blocked` statuses for downstream QA routing
- verify: count(subject="directly mirrored regression statuses", equals=3)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::RegressionRun.as_qa_result`
- tests: `workflows/tests/coder/qa/test_flow.py::test_a_failing_journey_suite_is_fixed_and_the_story_is_re_qad`

Private helpers keep the execution policy in one bounded module: `_run` invokes a shell-split
command and distinguishes timeout from failure to start; `_run_one` applies the five-state
classification and writes logs; `_merge_results` applies worst-first precedence; `_tail` supplies
diagnostic output; `_sanitize_label` creates safe log names; `_verification_index` reads the
sidecar index and falls back to legacy inline context; `_same_test_path` matches repository- and
service-relative paths; and `_attribute_failures` adds diagnostic owners without downgrading a
failure. The imported `RegressionSuite`, `RegressionSuites`, and `FailureAttribution` models are
the larger shared QA schema contract and are the next bounded descent item.
