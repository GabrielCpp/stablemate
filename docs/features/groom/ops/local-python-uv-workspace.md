---
type: environment
slug: local-python-uv-workspace
title: Local Python uv workspace
---
# Local Python uv workspace

- selector: the local checkout whose `groom/pyproject.toml` is resolved by uv from the workspace root
- services:
  - python-runtime: the uv-managed Python environment used by the groom package; no network listener
  - groom-package: the local `groom` import package installed from the checkout; no network listener
- backing:
  - uv-lock-resolution: the repository-root `uv.lock` pins dependencies for the uv workspace
  - package-index: uv may consult the configured Python package index when dependencies are not cached
- local-only: true
- code: pyproject.toml
- code: groom/pyproject.toml
- config: `uv.lock`
- verify: exit_status(code=0)

This environment is the local Python execution context for groom development. The package
manifest requires Python 3.12 or newer, declares the runtime dependencies and test extra, and
defines the wheel contents; the root manifest declares the uv workspace that includes `groom`,
and `uv.lock` fixes the resolved dependency graph. Runbook steps use the resulting environment
through `uv run` from the repository root.

