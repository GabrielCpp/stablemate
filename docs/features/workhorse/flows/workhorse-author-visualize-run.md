---
type: flow
slug: workhorse-author-visualize-run
title: Author, visualize, and run a workflow
---
# Author, visualize, and run a workflow

The design-time path from a hand-authored `workflow.yaml` to a live run: write the graph per the
[workflow file format](../workflow-format.md), sanity-check its shape with
[`workhorse dot`](../workhorse.md#dot) — optionally carving out one mode's view with `--pin`/
`--leaf` — before committing to a real, unattended [`workhorse run`](../workhorse.md#run) of the
same file.

- start: a `workflow.yaml` on disk (a `start` node id, a `nodes:` list, optionally `vars`/`env`/
  `flows:`) that has never been executed — authored directly or copied from
  [the format's sample](../workflow-format.md#sample-load-valid).
- steps:
  1. **Author the graph** against [the workflow file format](../workflow-format.md) — pick a
     `start` node, add `agent`/`script`/`branch`/`flow`/`call`/`terminal`/`fail`
     [nodes](../workflow-format.md#node-types) with resolvable `next`/`cases`/`conditions`/
     `default` targets, and any `vars`/`env`/[`flows:`](../workflow-format.md#flows) the graph
     needs. [`load_workflow`](../concepts/load-workflow.md) is the parser that will later validate
     it; nothing runs yet.
  2. **Sanity-check the shape** with [`workhorse dot --workflow <path>`](../workhorse.md#dot) —
     `_run_dot` resolves the path, parses it via
     [`load_workflow`](../concepts/load-workflow.md) (a `ValueError` here means the graph is
     malformed and the journey stops before any node runs), then renders it to Graphviz DOT via
     [`to_dot`](../concepts/dot-renderer.md). A multi-mode graph (a `branch` node whose value picks
     between subgraphs) can be carved down to one mode's view with repeated
     `--pin path=value` — collapsing that branch to its single resolved edge and pruning the
     unreachable side by [`to_dot`'s reachability walk](../concepts/dot-renderer.md#algorithm) — and
     `--leaf <node>` cuts off a specific node's outgoing edges to stop the walk at a cross-view
     bridge not gated by any pinned branch. The DOT text is written to stdout (or `-o <file>`) for
     visual inspection with any Graphviz renderer — a step outside workhorse itself. Bad node
     references, an unreachable node, or a graph that doesn't collapse the way `--pin` intended
     surface here as a visibly wrong diagram, before an agent turn or script has run.
  3. **Iterate.** Steps 1-2 repeat until the rendered graph's shape matches intent — no runtime
     cost to re-running `dot`, since it never executes a node.
  4. **Run it for real** with [`workhorse run --workflow <path> [<flow>]`](../workhorse.md#run) —
     `_run_run` resolves the same `workflow_path` (verbatim, since it's a path not a bare library
     name), selects the `--cli` [AgentBackend](../concepts/agent-backend.md), resolves fresh-start
     vs. resume, and hands the graph to
     [Workflow execution](../concepts/workflow.md#execution), which walks it node by node —
     checkpointing after each — exactly as diagrammed in step 2 (`--pin`'s collapsed branch is a
     rendering aid only; the live run still evaluates every `branch` node against the real
     context).
- end: the process exits `0` (reached a `terminal` node) or `1` (reached a `fail` node, hit a
  malformed workflow at load, or died unrecovered per
  [Workflow execution](../concepts/workflow.md#resilience-fail-soft)); on a genuine run,
  [run artifacts](../run-artifacts.md) under `<runs_dir>/<name>-<run_id>` record the outcome and
  make it resumable, continuing the [crash-and-resume](workhorse-crash-resume.md) journey if it
  dies mid-graph.

