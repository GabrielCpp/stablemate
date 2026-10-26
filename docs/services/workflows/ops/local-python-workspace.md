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
- code: `pyproject.toml` @c6134826cf5f
- code: `uv.lock` @0050e01b5233
- code: `workflows/pyproject.toml` @bb2bae459ece

This environment is the local execution context for the `workflows` distribution. The root
`pyproject.toml` declares the uv workspace and its shared development tools; `uv.lock` fixes the
resolved package versions; and `workflows/pyproject.toml` declares the workflow dependencies and
the six `workhorse-*` console scripts: `workhorse-loop-runner`, `workhorse-research`, `workhorse-author`, `workhorse-coder`, `workhorse-okf-book` and `workhorse-new`. It does not boot an HTTP service or require a host/port.

`make sync` must be run from the repository root with `uv sync --all-packages`, so every workspace
member is installed into the shared environment. `make -C workflows test` runs the workflow package
tests from that environment, while the root Makefile's workflow targets use the same interpreter.
The environment is local-only because its interpreter and source checkout are developer-machine
resources; a tool targeting a different machine or a packaged deployment is not this environment.

The workspace root declares the umbrella member `stablemate` beside `groom`, so `uv sync --all-packages` installs it too. The workflows package pins the Workhorse 4.x engine and the ostler 3.x library.
