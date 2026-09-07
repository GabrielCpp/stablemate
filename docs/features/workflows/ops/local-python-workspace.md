---
type: environment
slug: local-python-workspace
title: Local Python workspace
---
# Local Python workspace

- selector: the repository checkout whose root contains `pyproject.toml` and `uv.lock`; workflow commands resolve from its root `.venv`
- services:
  - python-runtime: the repository-root `.venv` interpreter; no network listener
  - workflow-console-scripts: the `.venv/bin` entry points declared by `workflows/pyproject.toml`; no network listener
- backing:
  - uv-lock-resolution: `uv.lock` supplies the pinned dependency graph for the workspace members
  - package-index: PyPI is consulted by `uv sync --all-packages` when a dependency is not already cached
- local-only: true
- code: `pyproject.toml`
- code: `uv.lock`
- code: `workflows/pyproject.toml`
- tests: `workflows/tests/test_hello_world.py::test_the_documented_command_is_declared`
- verify: exit_status(code=0)

This environment is the local execution context for the `workflows` distribution. The root
`pyproject.toml` declares the uv workspace and its shared development tools; `uv.lock` fixes the
resolved package versions; and `workflows/pyproject.toml` declares the workflow dependencies and
the five `workhorse-*` console scripts. It does not boot an HTTP service or require a host/port.

`make sync` must be run from the repository root with `uv sync --all-packages`, so every workspace
member is installed into the shared environment. `make -C workflows test` runs the workflow package
tests from that environment, while the root Makefile's workflow targets use the same interpreter.
The environment is local-only because its interpreter and source checkout are developer-machine
resources; a tool targeting a different machine or a packaged deployment is not this environment.

The console-script test checks that `workhorse-hello-world` is declared and points at a callable
entry point. The companion dry-run test exercises the same installed package contract without an
agent CLI; the environment-level verification is the successful exit status of that setup/run path.
