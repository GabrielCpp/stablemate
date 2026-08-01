---
type: flow
slug: workhorse-setup-and-run
title: Install a workflow and run it
---
# Install a workflow and run it

The first-time path from an empty environment to a finished run. There is **no
configuration step and nothing to point at a workflow**: a workflow is a Python
distribution that declares its own [`workhorse-<name>`](../workflow-format.md#console-script)
command, so *installing* it is what puts that command on `PATH`. (The retired YAML
front-end needed `config set-library` first, because a bare name had to be resolved against
a directory of `workflow.yaml` files. Its entry-point-group successor is gone too — the
command carries the workflow object, so there is no resolution step left to configure.)

- start: an environment with **no** workflow distribution installed — workhorse alone
  (`pip install workhorse-agent`) is a library and puts no command on `PATH` at all — plus
  an agent CLI on `PATH` for the [backend](../concepts/agent-backend.md) the run will use.
- steps:
  1. **Install a workflow distribution** — the bundled `workhorse-workflows`, a
     third-party one, or your own package (`pip install -e .`). It depends on
     `workhorse-agent`, so the engine arrives with it. Its `pyproject.toml` carries the
     [console script](../workflow-format.md#console-script) that becomes the command, and
     its `[project.dependencies]` are what the retired `requires:` preflight used to check:
     `pip`/`uv` resolve them here, before a run exists to fail.
  2. **[`workhorse-<name> run [<flow>]`](../workhorse.md#run)** — the command *is* the
     workflow, so there is nothing to name and nothing to be mistyped: a wrong command is a
     shell `command not found` rather than an engine error. The script hands the
     [`Registry`](../workflow-format.md#registry) straight to `run`, which calls
     [`Registry.directory()`](../workflow-format.md#registry) eagerly, so a zip-imported
     package — which has no directory for its `prompts/` to resolve against — fails at
     startup rather than at the first prompt render.
  3. **The driver walks the machine** — `run_pyflow` seeds or resumes the one stable run dir
     for `(workflow, run-id)`, selects the `--cli`
     [agent backend](../concepts/agent-backend.md), instantiates the entry
     [`Workflow`](../workflow-format.md#workflow-subclass) from `--params`, and hands it to
     [`drive`](../concepts/pyflow-driver.md), which enters the method named `start` and
     re-enters one state method per transition — checkpointing `(state, params)` before each
     — until a state returns `Done`.
- end: the process exits `0` (the entry flow returned
  [`Done`](../workflow-format.md#transition)), `1` (a `PyflowError` — an explicit
  `WorkflowFailed`, a dead state name, a checkpoint parameter the state does not have, or an
  exhausted transition budget — printed, with the run dir deliberately left resumable), or
  `130` (operator Ctrl-C, after `record_interrupt` stamps the pause). Either way the
  [run artifacts](../run-artifacts.md) under `<runs_dir>/<name>-<run_id>` record the outcome
  and make the run resumable from the state it stopped in — see
  [crash and resume](workhorse-crash-resume.md).
- verify: `workhorse/tests/test_console_script.py::test_a_registry_resolves_to_its_own_package_directory`,
  `workhorse/tests/test_console_script.py::test_the_cli_reports_the_zip_failure_and_exits`,
  `workhorse/tests/test_console_script.py::test_the_workflows_distribution_declares_its_scripts`
