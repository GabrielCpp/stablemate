# Coder Workflow Documentation

Visual and detailed documentation for the unified coder workflow.

## Files

- **[repo-modes.md](repo-modes.md)** — Mono-repo vs multi-repo: intended behavior
  - Read this before changing any `cwd:`/`add_dirs:` on an agent node, or any
    path-resolution script (`resolve-impl-context.py`, `resolve-review-context.py`,
    `find_repo_root`/`find_docs_root`)
  - The docs root is a separate concept from a workspace folder — no guarantee of
    git/`agents.yml`, may not be in the workspace list
  - Why `affected_repos`/`affected_repo_paths` can't always be relied on (standalone
    flow invocation)
  - What a "flow" is, and the standalone-vs-pipeline invocation contract

- **[multi-repo.md](multi-repo.md)** — Multi-repo operation guide
  - Workspace configuration (workspace file, per-repo agents.yml)
  - Operating modes (mono-repo vs multi-repo)
  - Planner contract (plan-context.json schema, `repo::path` notation)
  - QA modes (cli/playwright/maestro × local/dev)
  - Git operations (multi-repo branching, PRs)
  - Troubleshooting and migration from old format

- **[WORKFLOW.md](WORKFLOW.md)** — Complete workflow documentation
  - Mode overview (story vs epic)
  - Flow breakdowns with stage-by-stage details
  - Variable reference table
  - Implementation notes

- **coder-workflow-story.svg** — Diagram of story mode (single story, no queue/CI)
  - Entry: `branch_story` → `dev` (the per-story pipeline)
  - Exit: `done` or `qa_failed`

- **coder-workflow-epic.svg** — Diagram of epic mode (multi-story queue + CI/PR gating)
  - Entry: `init_base` → `select_story` → `dev`
  - Exit: `done` (all epics merged)

The per-story pipeline is three `flows:` sub-graphs — **`dev`** (plan + implement),
**`review`** (review + apply), and **`qa`** (the full QA gate cluster incl. the
adversarial auditor, regression + sentinel gates, and the QA operator gate). Each is
drawn as a dashed `flow: <name>` **cluster**, with a dashed "calls" edge from the
invoking phase node (`dev` / `review` / `qa_phase`) into the cluster's START. The
parent graph only sequences the phases and owns the queue-level escapes (the shared
`replan_epic`) and per-mode commit/PR finalize.

- **coder-workflow-story.dot** — GraphViz source for story mode diagram
- **coder-workflow-epic.dot** — GraphViz source for epic mode diagram

## Quick Start

Both modes share the same per-story stages:

1. **Plan** (with rework loop, max 3 cycles)
2. **Implement** (with review loop)
3. **QA** (with fix loop, max 3 cycles)

QA uses Ostler as the mandatory control plane: OKF impact context, one YAML plan for all
surfaces, four-state runner routing, runner-owned evidence, then deterministic verification
and adversarial audit.

Differences:

- **Story mode**: Single story, no queue/CI/PR. QA failure halts with non-zero exit.
- **Epic mode**: Queue-driven, CI/PR gating at epic boundaries, QA failure flags and continues.

See [WORKFLOW.md](WORKFLOW.md) for detailed stage breakdowns, variable reference, and implementation notes.

## Regenerating Diagrams

The `.dot` sources are generated directly from `workflow.yaml` by `workhorse dot`,
so they never drift from the workflow. `workflow.yaml` encodes both modes in one
graph (it starts at the `decide_mode` branch on `mode`), so each view is produced by
pinning `mode`; the story view additionally cuts the `replan_epic → select_story`
bridge (the rare "redirect to epic" escape hatch) so the epic queue/CI machinery
stays out of the story diagram. The three `flows:` sub-graphs (`dev` / `review` /
`qa`) render as clusters in **both** views (they are mode-agnostic).

```bash
cd docs/

# 1. Regenerate the GraphViz sources from workflow.yaml
workhorse dot --workflow ../workflow.yaml --pin mode=epic  --name epic_mode \
  -o coder-workflow-epic.dot
workhorse dot --workflow ../workflow.yaml --pin mode=story --name story_mode \
  --leaf replan_epic -o coder-workflow-story.dot

# 2. Render the SVGs from the sources (requires graphviz `dot`)
dot -Tsvg coder-workflow-story.dot -o coder-workflow-story.svg
dot -Tsvg coder-workflow-epic.dot -o coder-workflow-epic.svg
```
