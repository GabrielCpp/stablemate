---
type: cli
slug: workhorse-review-debt
title: workhorse-review-debt
---
# workhorse-review-debt

- binary: `workhorse-review-debt`
- code: `workflows/src/workhorse_workflows/review_debt/workflow.py::main` @69cce66c2aa2
- detail: [review-debt flow](flows/review-debt.md)
- detail: [review-debt package](concepts/review-debt-package.md)

Runs the review of the [debt register](../ostler/concepts/the-debt-register.md). One agent turn
groups every record by shared cause. The flow checks that the report names each record once,
writes `trends.md` beside the register, and proposes a decision for each cluster large enough to
need one. Workhorse provides the shared command parser, and this package registers the
`ReviewDebt` flow.

## Commands

### run
- usage: `workhorse-review-debt run [--params JSON] [--dry-run]`
- flags:
  - `--context-file PATH` selects the context manifest for this run.
  - `--params JSON` supplies checkpointed inputs, such as `max_sendbacks` and `decision_threshold`.
  - `--params-file PATH` supplies workflow parameters from a JSON object.
  - `--cli NAME`, `--profile NAME`, and `--config PATH` select the agent harness and configuration.
  - `--runs-dir DIR` and `--run-id ID` select the run-artifact location and stable identity.
  - `--dry-run` runs the registered stand-ins, which read an empty register, so the run ends at "register is empty" with no agent turn.
  - `--resume-run PATH`, `--resume-latest`, and `--no-cache` select resume or fresh-run behavior.
- does:
  - starts the registered `ReviewDebt` flow
- run: invoke(argv=["run", "--dry-run"])
- verify: stderr(matches="register is empty")
- fixture: none, because the dry run reads a stand-in register and writes nothing the check reads
- code: `workflows/src/workhorse_workflows/review_debt/workflow.py::main` @69cce66c2aa2
- detail: [review-debt flow](flows/review-debt.md)

### dot
- usage: `workhorse-review-debt dot [--name ID] [-o out.dot]`
- flags:
  - `--name ID` overrides the rendered graph identifier.
  - `-o, --output PATH` writes DOT output to a file instead of standard output.
- does:
  - renders the registered `ReviewDebt` state graph
- run: invoke(argv=["dot"])
- verify: exit_status(code=0)
- fixture: none, because the command reads only the installed package
- code: `workflows/src/workhorse_workflows/review_debt/workflow.py::main` @69cce66c2aa2

### version
- usage: `workhorse-review-debt version`
- does:
  - prints the installed Workhorse engine version
- run: invoke(argv=["version"])
- verify: exit_status(code=0)
- fixture: none, because the command reads only the installed package
- code: `workflows/src/workhorse_workflows/review_debt/workflow.py::main` @69cce66c2aa2
