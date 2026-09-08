---
type: concept
slug: workflows-orphan-classification
title: Workflows orphan classification rule
---
# Workflows orphan classification rule

- rule: An orphaned workflows doc is **intentionally link-free** if it is operationally reached (invoked directly by name, selected via configuration) rather than graph-reached (referenced by a composition-root or containing surface's `detail:` link). An orphaned doc is a **genuine gap** if it is referenced in code or configurations but lacks a reachable graph link.
- prefers: [runbooks and environments are operationally root-level](#operationally-rooted-orphans)
- deprecates: orphans that are referenced in composition-roots or code but lack `detail:` links from the places that use them

## Operationally-rooted orphans

**Runbooks** (7: `workhorse-author`, `workhorse-coder`, `workhorse-hello-world`, `workhorse-okf-builder`, `workhorse-research`, `make-target-drivers`, `coder-unit-tests`) document CLI entry points that users and operators invoke by name, not by following a graph edge. These are tools run interactively or in CI, selected by the user who needs them. They are correctly orphaned — a reader discovers them by learning which tool to invoke for a task, not by tracing composition-root edges.

**Environment** (`local-python-workspace`) is operationally selected via environment variable or configuration file, not reached via a graph link. It documents how to set up and use a specific runtime context.

**Verdict**: Runbooks and environment docs should remain link-free at the graph level. If discoverable documentation is needed (e.g., "which runbooks exist?"), that belongs in a prose index separate from the graph structure, linked from a service-level README or operations guide.

## Graph-referenced orphans requiring linking

The remaining 61 orphans are referenced in code or from other docs but lack `detail:` links from the places that use them, creating a discoverability gap. They fall into three categories:

**Prompt formats** (31 docs, e.g., `coder-code-review-prompt`, `survey-plan-prompt`): These are format/schema docs for prompts dispatched by flows. Each is referenced in code as `prompts/<role>.md` and loaded when a flow dispatches a turn with that prompt role. They should be linked via `detail:` from the flow step or composition-root that uses them, so a reader tracing `flow → step → prompt format` can follow the edges.

**Entry-point flows** (3 docs: `coder-genesis`, `coder-fix`, `walkthrough-web`): These are registered flows or gateway flows that are selectable by name from a composition-root CLI command. They should be linked from the composition-root's `detail:` bullets to show that they are registered entry points.

**Utility and schema concepts** (27 docs, e.g., `workflow-kit-*`, `coder-qa-schema-contracts`, `okf-builder-shared-*`): These are infrastructure and shared-contract concepts used across multiple flows, steps, or composition-roots. They should be linked from composition-roots or from the concepts/steps that consume them via `detail:` bullets.

**Verdict**: These 61 docs represent work items to add `detail:` links from the surfaces/concepts that reference them, so they become reachable from the graph. The linking targets are determined by where each orphan is used in code or config (e.g., prompt formats link from the flow that dispatches them, utility concepts link from composition-roots that import them).

