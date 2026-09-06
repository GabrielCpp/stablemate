---
type: environment
slug: workhorse-python-uv-workspace
title: workhorse Python uv workspace
---
# workhorse Python uv workspace

- selector: the local checkout whose `workhorse/pyproject.toml` is resolved by uv from the workspace root
- services:
  - python-runtime: the uv-managed Python environment used by the workhorse package; no network listener
  - workhorse-package: the local `workhorse` import package installed from the checkout; no network listener
- backing:
  - uv-lock-resolution: the repository-root `uv.lock` pins dependencies for the uv workspace
  - package-index: uv may consult the configured Python package index when dependencies are not cached
- local-only: true
- code: pyproject.toml
- code: workhorse/pyproject.toml
- config: `uv.lock`
- verify: exit_status(code=0)

This environment is the local Python execution context for workhorse development. The package
manifest requires Python 3.12 or newer, declares the runtime dependencies and test extra, and
defines the wheel contents; the root manifest declares the uv workspace that includes `workhorse`,
and `uv.lock` fixes the resolved dependency graph. The Makefile's `make install` runs `uv sync`
from `workhorse/`, while the other runbook steps use the resulting environment through `uv run`.

The environment is local-only because it depends on a developer checkout and its uv-managed
environment. It has no host, port, database, bucket, or emulator to boot.
