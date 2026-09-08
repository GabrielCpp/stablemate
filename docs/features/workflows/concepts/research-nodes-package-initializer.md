---
type: concept
slug: research-nodes-package-initializer
title: Research nodes package initializer
---
# Research nodes package initializer

The `workhorse_workflows.research.nodes` package groups deterministic work by subject and
establishes the shared blueprint for node registration. Importing this package registers every
node on the blueprint via their `@blueprint.node` decorators, and re-exports both the blueprint
and all node functions so the workflow composition can reach them through one package import.

The package contains four subject modules — `setup`, `program`, `measure`, and `publish` — each
grouping nodes by the concern they address. The blueprint itself is isolated in a submodule to
break circular import cycles: subject modules import the blueprint to register themselves, so the
blueprint cannot import them back.

- code: `workflows/src/workhorse_workflows/research/nodes/__init__.py`
- detail: [research deterministic nodes](research-deterministic-nodes.md)
- detail: [research workflow package initializer](research-workflow-package-initializer.md)

## Blueprint

### blueprint
- type: `Blueprint`
- semantics: the shared registration point for all research deterministic nodes
- code: `workflows/src/workhorse_workflows/research/nodes/_blueprint.py`
- code: `workflows/src/workhorse_workflows/research/nodes/_blueprint.py::blueprint`
- detail: [research deterministic nodes](research-deterministic-nodes.md)

## Subject modules

The following modules contain decorated nodes grouped by subject:

### setup
- semantics: checkout selection — clone the target repository or adopt an existing one
- contains: `clone_repo`

### program
- semantics: program manifest and ledger loading, and spend recording
- contains: `load_program`, `record_spend`

### measure
- semantics: detached job lifecycle, artifact classification, and fault diagnosis
- contains: `check_envelope`, `classify_fault`, `job_dir_for`, `submit_job`, `dry_run`, `watch_job`, `collect_job`, `kill_job`

### publish
- semantics: result publication — commit gate changes and push the result branch
- contains: `publish_results`

