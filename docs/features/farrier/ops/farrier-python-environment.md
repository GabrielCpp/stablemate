---
type: environment
slug: farrier-python-environment
title: Python and uv environment
---
# Python and uv environment

This is the local Python execution environment for the `farrier` distribution. The package is
resolved as a member of the repository-root uv workspace; its console script is available from the
shared `.venv`, and the package Makefile runs its tests through that environment. A separate
`pipx` installation is also supported for the published console script and has no repository
checkout requirement.

- selector: the repository checkout whose root `pyproject.toml` and `uv.lock` resolve the `farrier` workspace member
- services:
  - python-runtime: the repository-root `.venv` managed by uv; no network listener
  - farrier-console: the `farrier` console script installed from the local package; no network listener
  - pipx-console: an optional isolated `pipx` environment installed from the published `farrier` distribution; no network listener
- backing:
  - uv-lock-resolution: the repository-root `uv.lock` pins the dependency graph for all workspace members
  - package-index: uv may consult the configured Python package index when a locked dependency is not cached
- local-only: true
- code: farrier/pyproject.toml
- tests: `farrier/tests/test_pipx.py::test_a_pypi_install_has_no_local_path_to_mount`
- verify: exit_status(code=0)

The package requires Python 3.12 or newer, declares its runtime dependencies in
`farrier/pyproject.toml`, and exposes `farrier` through the `farrier.install:main` console-script
entry point. From the repository root, `uv sync --all-packages` installs every workspace member
into the shared environment. The package Makefile's `install` target runs `uv sync`, while its
`test` target runs `uv run pytest tests -q -n auto --dist worksteal` from `farrier/`; those targets
are operational drivers, not additional services.

The environment is local-only because its interpreter and source checkout are developer-machine
resources. Installing the published package with `pipx install farrier` or `uv tool install farrier`
creates an isolated console-script environment instead; it does not provide the workspace used by
the package Makefile. `pipx list --json` is the source used by Farrier's workflow discovery for
installed `workhorse-*` scripts, and a PyPI-installed distribution has no local source path to
mount.
