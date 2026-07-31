---
type: flow
slug: workhorse-author-test
title: Author and run a workflow's test suite
---
# Author and run a workflow's test suite

The path a workflow author follows to gain confidence in a state machine without touching a
real agent CLI or a real repo. A workflow is ordinary Python now, so its tests are ordinary
pytest: **construct the [`Workflow`](../workflow-format.md#workflow-subclass), hand
[`drive`](../concepts/pyflow-driver.md) a `RunEnv` whose dependencies are substituted, and
assert on what came back and what was written.** Nothing is monkeypatched and no subprocess
is spawned — the seam is the run's own node index, so a test replaces a dependency rather
than reaching into a module. [`workhorse test <dir>`](../workhorse.md#test) is the runner.
The narrative version of the seam, with a worked example, is
[AUTHORING.md](../../../../workhorse/docs/AUTHORING.md#the-node-index-is-the-substitution-seam).

- start: a workflow package with states, nodes and prompts but no `tests/` subdirectory yet,
  and `pytest` installed alongside it (`pip install 'workhorse-agent[test]'`).
- steps:
  1. **Create `<workflow_dir>/tests/test_*.py`.** Import the workflow's own classes plus
     `drive` and `RunEnv`; a test is a function, not a fixture-heavy harness.
  2. **Build a `RunEnv` for the run.** It carries the run's dependencies — the
     `ArtifactWriter` (point it at pytest's `tmp_path`), the workflow directory prompts
     resolve against, a `RunConfig`, and the seams below. Anything the test does not
     substitute behaves exactly as it would in production, which is the point: the driver,
     the checkpoint writer and the [artifact](../run-artifacts.md) layout are the real ones.
  3. **Substitute the dependencies the test wants to control**, all through the run's
     [node index](../workflow-format.md#registry):
     - `RunEnv(nodes=registry.override(clone_repo=lambda logger: RepoSetup(...)))` — a
       **copy** of the index with those names rebound, so a substitution cannot outlive the
       run that asked for it and a typo names the registered nodes instead of silently
       adding one.
     - `RunEnv(run_agent=scripted)` — the agent backend as a run dependency rather than a
       module attribute, so a test scripts a turn's reply without a CLI on `PATH`.
     - `Registry.stub_agents({stem: reply})` and `@blueprint.node(stub=…)` — declared
       stand-ins, shared with [`--dry-run`](../workhorse.md#run) rather than written twice.
  4. **Drive it: `result = drive(MyWorkflow(subject="login"), env)`.** The return value is
     whatever the entry flow's [`Done`](../workflow-format.md#transition) carried. A
     deliberate failure raises `WorkflowFailed` (or another `PyflowError`) — assert on the
     exception, and on the checkpoint the driver wrote before it.
  5. **Assert.** On the returned result, on the run dir's `checkpoint.json` / `run.json` /
     per-node `output.json`, and with the helpers `workhorse.testing` still provides:
     `make_git_repo(tmp_path)` for a workflow that expects a real repo, and `assert_file` /
     `assert_file_contains` / `assert_json_file` for what a node wrote to disk.
  6. **Run the suite** with [`workhorse test <workflow_dir> [-k FILTER] [-v]`](../workhorse.md#test)
     — `_run_test` confirms `<workflow_dir>/tests/` exists (else errors), confirms `pytest`
     is importable (else prints the `workhorse-agent[test]` install hint), then calls
     `pytest.main([<tests_dir>, …])` in-process and exits with pytest's own return code.
     Plain `pytest <workflow_dir>/tests` works identically; the subcommand only adds the two
     checks and the hint.
- end: the process exits `0` when every test under `<workflow_dir>/tests/` passes, and `1`
  if any test fails, `tests/` is missing, or `pytest` is not installed. Each test's run dir
  is left under pytest's `tmp_path` for post-mortem inspection. `workhorse`'s own
  `tests/test_pyflow.py` is written exactly this way and is the worked reference.
- verify: `workhorse/tests/test_pyflow.py::test_the_run_index_supplies_the_body_the_callsite_only_names`,
  `workhorse/tests/test_pyflow.py::test_the_run_agent_backend_is_a_run_dependency_not_a_module_attribute`,
  `workhorse/tests/test_pyflow.py::test_a_declared_stub_is_what_a_dry_run_runs_in_place_of_the_node`
