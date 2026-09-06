---
type: runbook
slug: farrier-cli-and-make-drivers
title: Farrier CLI and Make drivers
---
# Farrier CLI and Make drivers

- driver: cli
- environment: [Python and uv environment](farrier-python-environment.md)
- cli: [farrier CLI](../farrier.md)
- surfaces: [farrier CLI](../farrier.md)
- code: `farrier/Makefile::install`
- reuse: never
- boot-timeout: 120
- health-timeout: 30
- working-directory: farrier

This runbook drives the local Farrier package from the `farrier/` working directory. The console
script is installed by the shared uv environment and dispatches through `farrier.install:main` to
`farrier.cli:main`; the CLI surface and its subcommands are documented in the linked CLI node.
Make targets return the exit status of their command. `build` depends on `clean`, and `check`
depends on `build`, so the ordered sequence below deliberately exercises those dependencies before
the published-install check and final cleanup.

## Steps

### install-workspace

- kind: prepare
- run: `make install`
- working-directory: farrier
- timeout: 120
- produces: the Farrier package and its dependencies in the repository uv environment
- verify: [Farrier Makefile](../../../../farrier/Makefile)
- provenance: derived

### check-console

- kind: service
- run: `farrier --help`
- working-directory: farrier
- timeout: 30
- health: `farrier --help` exits 0 and prints the top-level command listing
- produces: the installed `farrier` console script is callable from the workspace environment
- verify: [farrier CLI](../farrier.md)
- provenance: derived

### show-help

- kind: run
- run: `make help`
- working-directory: farrier
- produces: the Makefile target listing for `help`, `install`, `test`, `build`, `check`, `verify-install`, `clean`, and `version`
- verify: [Farrier Makefile](../../../../farrier/Makefile)
- provenance: derived

### run-tests

- kind: run
- run: `make test`
- working-directory: farrier
- timeout: 120
- produces: the standalone Farrier pytest result
- verify: [Farrier test suite](farrier-tests.md)
- provenance: derived

### build-package

- kind: run
- run: `make build`
- working-directory: farrier
- timeout: 120
- produces: the Farrier source distribution and wheel in `farrier/dist/`
- verify: [Farrier Makefile](../../../../farrier/Makefile)
- provenance: derived

### check-wheel-contents

- kind: run
- run: `make check`
- working-directory: farrier
- timeout: 120
- produces: the wheel-content listing for the freshly built Farrier wheel
- verify: [Farrier Makefile](../../../../farrier/Makefile)
- provenance: derived

### verify-published-install

- kind: run
- run: `make verify-install`
- working-directory: farrier
- timeout: 120
- produces: the published Farrier package's top-level `--help` output
- verify: [farrier CLI](../farrier.md)
- provenance: derived

### clean-artifacts

- kind: run
- run: `make clean`
- working-directory: farrier
- produces: removal of `farrier/dist/`, `farrier/build/`, and `farrier/*.egg-info`
- verify: [Farrier Makefile](../../../../farrier/Makefile)
- provenance: derived

### show-version

- kind: run
- run: `make version`
- working-directory: farrier
- produces: the Farrier distribution name and declared version
- verify: [Farrier Makefile](../../../../farrier/Makefile)
- provenance: derived
