---
type: concept
slug: ops-runbooks
title: Operational runbooks index
---
# Operational runbooks index

This page indexes the operational runbooks and environments that support the workflows package. Runbooks document how to exercise a surface — a CLI, an HTTP service, a browser application — from source in local development or in test environments.

**Driver runbooks** exercise each Workhorse CLI in dry-run mode with checkpointed inputs:

- [workhorse-author driver](../ops/workhorse-author.md) — exercises the author registry with seeded flow and roadmap inputs
- [workhorse-coder driver](../ops/workhorse-coder.md) — exercises the coder registry with checkpointed story and epic selection
- [workhorse-hello-world driver](../ops/workhorse-hello-world.md) — exercises the greeting example
- [workhorse-okf-builder driver](../ops/workhorse-okf-builder.md) — exercises the backfill registry with seeded repo and builder inputs
- [workhorse-research driver](../ops/workhorse-research.md) — exercises the research gate loop

**Test harnesses** drive the workflow composition roots with real workflow nodes and agent boundaries replaced by seams:

- [Coder unit tests](../ops/coder-unit-tests.md) — pytest tier exercising the Coder workflow composition root against isolated temporary repositories

**Build and setup**:

- [Make-target drivers](../ops/make-target-drivers.md) — repository-level Make interface for workspace setup, gates, builds, and release dispatch
- [Local Python workspace](../ops/local-python-workspace.md) — the uv-managed Python environment and pinned dependencies for the workflows package

