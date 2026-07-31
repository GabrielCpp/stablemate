---
type: flow
slug: workhorse-setup-and-run
title: Install a workflow and run it
---
# Install a workflow and run it

The first-time path from a bare `workhorse` install to a finished run. There is **no
configuration step**: a workflow is a Python distribution that publishes its name in the
`workhorse.workflows` entry-point group, so *installing* it is what makes
[`workhorse run <name>`](../workhorse.md#run) able to find it. (The retired YAML front-end
needed `workhorse config set-library` first, because a bare name had to be resolved against
a directory of `workflow.yaml` files. That directory no longer exists, and `library_dir` no
longer participates in resolution.)

- start: a `workhorse` install (`pip install workhorse-agent`) with **no** workflow
  distribution installed alongside it — `workhorse run acme` would report the name as
  unknown and print the sorted list of what *is* installed, which is empty — plus an agent
  CLI on `PATH` for the [backend](../concepts/agent-backend.md) the run will use.
- steps:
  1. **Install a workflow distribution** into the same environment as `workhorse` — the
     bundled `workhorse-workflows`, a third-party one, or your own package
     (`pip install -e .`). Its `pyproject.toml` carries the
     [entry point](../workflow-format.md#entry-point) that publishes the name, and its
     `[project.dependencies]` are what the retired `requires:` preflight used to check:
     `pip`/`uv` resolve them here, before a run exists to fail. A distribution may also
     publish a [console script](../workflow-format.md#console-script), giving the same
     workflow a second front door as `workhorse-<name>`.
  2. **[`workhorse run <name> [<flow>]`](../workhorse.md#run)** — the name is required, and a
     **path** is refused *by name*: anything carrying a path separator or a `.yaml`/`.yml`
     suffix, or naming a file that already exists, is reported as a path rather than
     silently misread as a name. The name is looked up in the entry-point group; an unknown
     one prints the installed names. Resolution then calls
     [`Registry.directory()`](../workflow-format.md#registry) eagerly, so a zip-imported
     package — which has no directory for its `prompts/` to resolve against — fails at
     resolution rather than at the first prompt render.
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
- verify: `workhorse/tests/test_packaged_workflows.py::test_entry_point_resolves_to_package_directory`,
  `workhorse/tests/test_packaged_workflows.py::test_an_unknown_name_lists_what_is_installed`,
  `workhorse/tests/test_workflow_resolution.py::test_a_path_is_reported_as_a_path_not_as_an_unknown_name`
