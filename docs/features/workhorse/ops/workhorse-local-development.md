---
type: runbook
slug: workhorse-local-development
title: workhorse local development
---
# workhorse local development

- driver: cli
- environment: [workhorse Python uv workspace](workhorse-python-uv-workspace.md)
- cli: [workhorse](../workhorse.md)
- surfaces: [workhorse](../workhorse.md)
- code: `workhorse/Makefile::help`
- working-directory: workhorse

This runbook is the package-local development interface for the workhorse library, linked from
the [workhorse CLI surface](../workhorse.md). It runs from `workhorse/`; `make help` is the default
driver and lists every available package task. The Makefile delegates dependency installation,
tests, packaging, wheel inspection, published-package import verification, build-artifact cleanup,
and version reporting to uv, pytest, and the package metadata. It does not start a network service.

## Steps

### help

- kind: prepare
- run: `make help`
- working-directory: workhorse
- timeout: 30
- produces: the available package-local Make targets and their descriptions
- verify: [workhorse Makefile](../../../../workhorse/Makefile)
- provenance: derived

### install

- kind: service
- run: `make install`
- working-directory: workhorse
- timeout: 120
- health: `uv run python -c "import workhorse"` exits 0 after the local package environment is available
- provenance: derived

### test

- kind: run
- run: `make test`
- working-directory: workhorse
- timeout: 120
- produces: pytest results for `workhorse/tests`
- verify: [workhorse Makefile](../../../../workhorse/Makefile)
- provenance: derived

### build

- kind: run
- run: `make build`
- working-directory: workhorse
- timeout: 120
- produces: the `workhorse-agent` source distribution and wheel in `workhorse/dist/`
- verify: [workhorse Makefile](../../../../workhorse/Makefile)
- provenance: derived

### check

- kind: run
- run: `make check`
- working-directory: workhorse
- produces: the built wheel's file listing
- verify: [workhorse Makefile](../../../../workhorse/Makefile)
- provenance: derived

### verify-install

- kind: run
- run: `make verify-install`
- working-directory: workhorse
- timeout: 120
- produces: the imported `workhorse.console_script` public API from the refreshed published package
- verify: [workhorse Makefile](../../../../workhorse/Makefile)
- provenance: derived

### clean

- kind: prepare
- run: `make clean`
- working-directory: workhorse
- timeout: 30
- produces: removal of `workhorse/dist/`, `workhorse/build/`, and `workhorse/*.egg-info`
- verify: [workhorse Makefile](../../../../workhorse/Makefile)
- provenance: derived

### version

- kind: run
- run: `make version`
- working-directory: workhorse
- produces: the `workhorse-agent` distribution name and declared version
- verify: [workhorse Makefile](../../../../workhorse/Makefile)
- provenance: derived
