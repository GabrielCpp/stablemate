---
type: runbook
slug: workhorse-root-make-drivers
title: workhorse root Make drivers
---
# workhorse root Make drivers

- driver: cli
- environment: [workhorse Python uv workspace](workhorse-python-uv-workspace.md)
- cli: [workhorse](../workhorse.md)
- surfaces: [workhorse](../workhorse.md)
- code: `Makefile::help`
- working-directory: .

This runbook is the repository-root operational interface for the workhorse workspace. It is
executed from the checkout root, unlike the [package-local development runbook](workhorse-local-development.md),
which is executed from `workhorse/`. The root Makefile coordinates the shared uv environment,
browser and hook setup, workspace lint and test gates, repository guards, vendoring, package
builds, version reporting, and release dispatch. It does not start a network service; the
`install` step's import probe confirms that the environment needed by the other drivers is ready.

The `include` step documents the generated `.agents/agents.mk` include that supplies launcher
targets when agent installation has rendered it. GNU Make reads that file while processing any
root target; it is not a separate phony target.

## Steps

### help

- kind: prepare
- run: `make help`
- working-directory: .
- timeout: 30
- produces: the root Make target inventory and descriptions
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### install

- kind: service
- run: `make install`
- working-directory: .
- timeout: 300
- health: `uv run python -c "import workhorse"` exits 0 after the workspace environment, Chromium, and git hooks are installed
- provenance: derived

### sync

- kind: prepare
- run: `make sync`
- working-directory: .
- timeout: 300
- produces: the uv workspace environment resolved for all members from `uv.lock`
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### browsers

- kind: prepare
- run: `make browsers`
- working-directory: .
- timeout: 300
- produces: the Chromium browser binary used by Playwright
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### hooks

- kind: prepare
- run: `make hooks`
- working-directory: .
- timeout: 120
- produces: the repository git hooks for private-name, commit-message, and generated-file guards
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### lint

- kind: run
- run: `make lint`
- working-directory: .
- timeout: 600
- produces: ruff, ty, and basedpyright results for the complete workspace
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### test

- kind: run
- run: `make test`
- working-directory: .
- timeout: 1200
- produces: package test results and every repository guard result
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### bench-doctor

- kind: run
- run: `make bench-doctor DOCS=<path> [JSON=1]`
- working-directory: .
- timeout: 600
- produces: timing measurements for `ostler doctor` over the book at `DOCS`, optionally as JSON
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### okf-verify

- kind: run
- run: `make okf-verify`
- working-directory: .
- timeout: 600
- produces: the OKF coverage result for every documented book and source inventory
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### test-scripts

- kind: run
- run: `make test-scripts`
- working-directory: .
- timeout: 600
- produces: pytest results for repository guard scripts
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### check-public

- kind: run
- run: `make check-public`
- working-directory: .
- timeout: 300
- produces: the public/private-name and base-stands-alone guard result
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### check-no-env

- kind: run
- run: `make check-no-env`
- working-directory: .
- timeout: 120
- produces: the guard result for workflow input access through parameters instead of environment variables
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### check-no-giveup

- kind: run
- run: `make check-no-giveup`
- working-directory: .
- timeout: 120
- produces: the guard result that budget exhaustion remains blocked rather than failed
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### check-no-shell

- kind: run
- run: `make check-no-shell`
- working-directory: .
- timeout: 120
- produces: the guard result for ad-hoc shell scripts outside the unified CLI
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### check-fixtures

- kind: run
- run: `make check-fixtures`
- working-directory: .
- timeout: 300
- produces: the declared-fixture consistency result for the benchmark corpus
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### check-prompt-agnostic

- kind: run
- run: `make check-prompt-agnostic`
- working-directory: .
- timeout: 120
- produces: the guard result that coder prompts do not name a specific application stack
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### check-parsers

- kind: run
- run: `make check-parsers`
- working-directory: .
- timeout: 120
- produces: the guard result that structured formats use parsers rather than regex matching
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### check-portability

- kind: run
- run: `make check-portability`
- working-directory: .
- timeout: 120
- produces: the portability-tier guard result for shipped packages
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### check-library

- kind: run
- run: `make check-library`
- working-directory: .
- timeout: 300
- produces: the strict base-library front-matter validation result
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### check-agent-outputs

- kind: run
- run: `make check-agent-outputs`
- working-directory: .
- timeout: 300
- produces: the generated agent-adapter freshness result
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### check-skills

- kind: run
- run: `make check-skills`
- working-directory: .
- timeout: 120
- produces: the base-library skill writing-doctrine guard result
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### vendor

- kind: run
- run: `make vendor`
- working-directory: .
- timeout: 120
- produces: refreshed copies of `core/stablemate_core` in the vendoring destinations
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### check-vendor

- kind: run
- run: `make check-vendor`
- working-directory: .
- timeout: 120
- produces: the byte-for-byte vendored-copy consistency result
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### build

- kind: run
- run: `make build`
- working-directory: .
- timeout: 600
- produces: source distributions and wheels in the published package `dist/` directories
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### version

- kind: run
- run: `make version`
- working-directory: .
- timeout: 60
- produces: the declared versions of every published package
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### release

- kind: run
- run: `make release`
- working-directory: .
- timeout: 120
- produces: a dispatched release workflow and the command used to find its pending release PR
- verify: [root Makefile](../../../../Makefile)
- provenance: derived

### include

- kind: prepare
- run: `make -n help`
- working-directory: .
- timeout: 30
- produces: the dry-run expansion after GNU Make loads `.agents/agents.mk` when that generated include exists
- verify: [root Makefile](../../../../Makefile)
- provenance: derived
