---
type: flow
slug: workhorse-crash-resume
title: Crash and resume in place
---
# Crash and resume in place

The headline resilience path: [`workhorse run`](../workhorse.md#run) checkpoints after every node
so an unattended run that dies mid-graph (process killed, machine reboot, `OutOfGasError`, an
unrecovered `BackendInvocationError`) is never re-launched from scratch — re-issuing the **identical
command line** finds the stable run dir's [`checkpoint.json`](../run-artifacts.md#checkpointjson)
and continues from exactly where it stopped, per
[Workflow execution](../concepts/workflow.md#execution) steps 4-5.

- start: an in-progress `workhorse run <workflow> [<flow>]` invocation dies after at least one
  [`write_checkpoint`](../concepts/artifact-writer.md#write_checkpointcurrent_id-context) call for
  its stable run dir `<runs-dir>/<workflow-name>-<run-id>`, before the run reached a
  `terminal`/`fail` node — so `run.json`'s `terminal` key is still `null`.
- steps:
  1. [`workhorse run <workflow> [<flow>]`](../workhorse.md#run) — re-run the exact same command
     (same workflow/path, same `--run-id` or default, same `--runs-dir`), with none of
     `--resume-run`/`--resume-latest`/`--no-cache` given. `_run_run` resolves the same
     `workflow_path`, `runs_dir`, and `run_id` as the crashed invocation and calls `run(...,
     auto=True)` with `resume_run_dir=None` — auto-resume-in-place, not an explicit resume flag,
     drives this path.
  2. [Auto-resolve the run dir](../concepts/workflow.md#execution) (`_auto_resolve`, step 4) —
     computes the one stable dir for `(graph.name, run_id or "default")`, the same directory the
     crashed run was writing to. Because it holds an unfinished
     [`checkpoint.json`](../run-artifacts.md#checkpointjson) (`run.json`'s `terminal` still `null`,
     since the crash pre-empted `finish()`), that dir becomes this invocation's `resume_run_dir`
     instead of triggering a fresh start.
  3. [Resume the writer and checkpoint](../concepts/workflow.md#execution) (step 5, resume branch)
     — [`ArtifactWriter.resume`](../concepts/artifact-writer.md#resumerun_dir---artifactwriter-classmethod)
     re-binds to that dir and reads back [`checkpoint.json`](../run-artifacts.md#checkpointjson):
     `current_id` (the node that was about to run, or had just finished, when the crash hit) and the
     full context at that point. `ctx` restarts from `{manifest, checkpoint["context"]}`.
  4. [`_should_fast_forward`](../concepts/workflow.md#execution) — checks `current_id`'s
     [`done.json`](../run-artifacts.md#node-iddonejson): if it exists, its `seq` matches the
     checkpoint's `seq`, and it names a `next` — the node finished its side effects and wrote its
     completion marker, but the crash landed in the gap before the walk's next
     `write_checkpoint` advanced the cursor — restore `ctx` from that node's
     [`context_after.json`](../run-artifacts.md#node-idcontext_afterjson) and jump `current_id`
     straight to `done["next"]`, so the finished node's side effects (a git commit, a PROGRESS
     append, an agent turn) are never re-run. Otherwise `current_id` re-enters as-is with
     `resume_interrupted_node = True`, the one case where an `agent` node continues its prior
     backend session instead of starting fresh.
  5. [Node-walk engine](../concepts/workflow.md#node-walk-engine) (`_step_loop`) — steps the graph
     forward from that `current_id` exactly as a fresh run would: burn gas, `write_checkpoint`,
     dispatch by node type, merge outputs, `write_step`/`write_branch`, advance to `next` — until it
     reaches a `terminal`/`fail` node.
- end: the walk reaches a `terminal` node — `write_final_context` then `finish(terminal="terminal")`
  stamp [`context.json`](../run-artifacts.md#contextjson) and
  [`run.json`](../run-artifacts.md#runjson)'s `ended_at`/`terminal`, and the process exits `0`. (A
  `fail` node, or dying again with an unrecovered `OutOfGasError`/`BackendInvocationError`, exits `1`
  and leaves the same stable dir resumable for another retry of this same journey.)
- verify: `workhorse/tests/test_idempotency.py::test_should_fast_forward_matches_only_current_checkpoint`,
  `workhorse/tests/test_resume_auto.py::test_auto_resolve_skips_terminal_run`,
  `workhorse/tests/test_resume_auto.py::test_auto_resolve_single_stable_dir_per_program`

