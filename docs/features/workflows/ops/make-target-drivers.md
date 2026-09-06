---
type: runbook
slug: make-target-drivers
title: Make-target drivers
---
# Make-target drivers

- driver: cli
- code: [`Makefile::install`](../../../../Makefile)
- working-directory: .

This runbook documents the repository's Make-driven operational interface. The workspace
targets run from the repository root; package targets delegated to `workflows/Makefile` run
from `workflows/`. The generated `include .agents/agents.mk` line adds the Farrier launcher
targets when that file exists; it is part of the root Makefile's command surface but is not a
second workflow stack. Targets return the exit status of their delegated command, so a non-zero
status stops the target and its dependent target chain.

## Steps

### sync-workspace

- kind: service
- run: `make sync`
- working-directory: .
- timeout: 120
- health: `uv run python -c "import workhorse_workflows"` exits 0 after all workspace packages are importable
- provenance: derived

### show-help

- kind: run
- run: `make help`
- working-directory: .
- produces: the workspace target help listing
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### install-workspace

- kind: run
- run: `make install`
- working-directory: .
- produces: the synced workspace, Chromium browser installation, and installed git hooks
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### install-browsers

- kind: run
- run: `make browsers`
- working-directory: .
- produces: the Playwright Chromium browser binary
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### install-hooks

- kind: run
- run: `make hooks`
- working-directory: .
- produces: configured git hooks under `.githooks/`
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### lint-workspace

- kind: run
- run: `make lint`
- working-directory: .
- produces: zero-findings ruff, ty, and basedpyright results for the workspace
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### test-workspace

- kind: run
- run: `make test`
- working-directory: .
- produces: aggregate package-test and repository-guard results
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### benchmark-doctor

- kind: run
- run: `make bench-doctor DOCS=<path> [JSON=1]`
- working-directory: .
- timeout: 120
- produces: the measured Ostler doctor timing for the supplied external book
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### verify-okf

- kind: run
- run: `make okf-verify`
- working-directory: .
- produces: OKF coverage verification results for every book and its source
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### test-repository-scripts

- kind: run
- run: `make test-scripts`
- working-directory: .
- produces: pytest results for repository guard scripts
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### check-public-boundary

- kind: run
- run: `make check-public`
- working-directory: .
- produces: a pass only when tracked content and reachable history contain no configured private names and the public base stands alone
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### check-no-environment

- kind: run
- run: `make check-no-env`
- working-directory: .
- produces: a pass only when workflow source does not read process environment values
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### check-no-give-up

- kind: run
- run: `make check-no-giveup`
- working-directory: .
- produces: a pass only when the deleted give-up control-flow vocabulary is absent
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### check-no-shell

- kind: run
- run: `make check-no-shell`
- working-directory: .
- produces: a pass only when no unapproved shell script is tracked
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### check-fixtures

- kind: run
- run: `make check-fixtures`
- working-directory: .
- produces: declared-fixture consistency results for the benchmark corpus
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### check-prompt-agnostic

- kind: run
- run: `make check-prompt-agnostic`
- working-directory: .
- produces: a pass only when coder prompts do not hard-code a technology stack
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### check-parsers

- kind: run
- run: `make check-parsers`
- working-directory: .
- produces: structured-document parser-boundary results
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### check-portability

- kind: run
- run: `make check-portability`
- working-directory: .
- produces: portability-tier guard results
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### check-library

- kind: run
- run: `make check-library`
- working-directory: .
- produces: strict base-library front-matter validation results
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### check-agent-outputs

- kind: run
- run: `make check-agent-outputs`
- working-directory: .
- produces: generated-agent-adapter drift results
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### check-skills

- kind: run
- run: `make check-skills`
- working-directory: .
- produces: base-library skill-writing guard results
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### vendor-core

- kind: run
- run: `make vendor`
- working-directory: .
- produces: refreshed vendored core copies in the dependent packages
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### check-vendor

- kind: run
- run: `make check-vendor`
- working-directory: .
- produces: byte-for-byte vendored-core consistency results
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### build-workspace

- kind: run
- run: `make build`
- working-directory: .
- produces: package source distributions and wheels in each published package's `dist/` directory
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### show-versions

- kind: run
- run: `make version`
- working-directory: .
- produces: the declared version of every published package
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### dispatch-release

- kind: run
- run: `make release`
- working-directory: .
- produces: a dispatched release workflow; merging its release-please pull request performs publication
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### include-agent-launchers

- kind: prepare
- run: `make help` with the generated `.agents/agents.mk` included when present
- working-directory: .
- produces: the additional Farrier agent launcher targets supplied by `.agents/agents.mk`
- verify: [workspace Makefile](../../../../Makefile)
- provenance: derived

### show-package-help

- kind: run
- run: `make -C workflows help`
- working-directory: .
- produces: the workflows package target help listing
- verify: [workflows Makefile](../../../../workflows/Makefile)
- provenance: derived

### test-workflows-package

- kind: run
- run: `make -C workflows test`
- working-directory: .
- timeout: 120
- produces: pytest results for the workflows package
- verify: [workflows Makefile](../../../../workflows/Makefile)
- provenance: derived

### build-workflows-package

- kind: run
- run: `make -C workflows build`
- working-directory: .
- produces: the workflows package source distribution and wheel in `workflows/dist/`
- verify: [workflows Makefile](../../../../workflows/Makefile)
- provenance: derived

### show-workflows-version

- kind: run
- run: `make -C workflows version`
- working-directory: .
- produces: the workflows distribution name and version
- verify: [workflows Makefile](../../../../workflows/Makefile)
- provenance: derived

### clean-workflows-package

- kind: run
- run: `make -C workflows clean`
- working-directory: .
- produces: removal of `workflows/dist`, `workflows/build`, and `workflows/*.egg-info`
- verify: [workflows Makefile](../../../../workflows/Makefile)
- provenance: derived
