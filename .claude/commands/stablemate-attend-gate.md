---
description: "Attend one stopped run — a parked operator gate or a dead run — by diagnosing it, patching stablemate, and then reloading-and-answering or resuming it"
argument-hint: "<run-id> | (dispatched by groom with the job appended)"
metadata:
  generated_by: farrier
  source: library/prompts/stablemate/attend-gate.md
  resolve: "farrier source .claude/commands/stablemate-attend-gate.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# Attend a stopped run

A run that parked on an operator gate, or died, cannot clear itself: it cannot patch the
code it is executing, and a dead run cannot be investigated by the process that died.
That is the whole reason you are here rather than inside it. You are outside it, you can
change the code underneath it, and you can then let it continue from exactly where it
stopped.

The job — which run, which kind of stop, and the gate body or failure handoff verbatim —
is **appended below this prompt**, under `## The run that stopped`. It arrives unparsed
on purpose: three incompatible gate formats are in the tree (composed `coder`
escalations, hand-written f-strings, raw validator dumps), and handing the text over
intact is the only thing that covers all of them. Read it as prose, not as fields.

If you were invoked by hand with a run id instead, resolve the rest yourself:

```bash
groom status --json     # run_id, workflow, run_dir, workspace
```

$ARGUMENTS

## The rules that do not bend

**Never answer a gate to make the run move.** An answer asserts that the cause is fixed
and verified. If it is not, there are exactly two honest outcomes: fix it, or leave the
gate armed and write what you found. An answer that unsticks a run buys one lap and costs
the next reviewer the whole investigation.

**Read what was already tried.** A gate body opens with what blocked and what the
auto-resolver already ruled out. That list is the diagnosis so far — answering without
reading it re-runs dead ends an unbounded resolver turn already paid for.

**Reload first, answer second.** The run re-arms its wait on re-entry and only re-parks
while the file still reads `AWAITING_OPERATOR`. An answer written *before* a reload that
would have cut in lets the run resume on the **old** code: the gate clears, the dashboard
goes green, and the defect is still there. That is the failure that looks like success.

**You may resume. You may never discard a checkpoint or start a run fresh.** Terminating
a run, or throwing away its state, is the operator's call and stays the operator's call.

**`run_dir` is always absolute.** A bare `--run <id>` resolves under the *current*
directory's `.agents/runs`, which is not where these runs live. Take the workspace from
the job, never from memory — runs live in repos other than this one.

## A parked run

1. **Ask the run what it is waiting on.** Its own answer is authoritative, including its
   spelling of the gate path:

   ```bash
   workhorse-<workflow> control --run <abs run_dir> questions
   ```

2. **Investigate.** The gate file, then `checkpoint.json`, `events.jsonl`,
   `inbox.jsonl`, and the source the gate names.

3. **Patch the cause**, in `workhorse/` or `workflows/` — failures at this layer are
   overwhelmingly workflow bugs, workhorse bugs, or a prompt needing tuning, not the
   target repo's content. Then run the gate: `make lint` from the repo root, plus the
   affected test package. **A failing verification ends the attempt** — write the
   diagnosis to the run's `inbox.jsonl` and leave the gate armed. Commit and push the
   fix, so the reload has something to pick up.

   A blocker that is the run's *environment* — a stack that will not come up, a missing
   binary, a seeded fixture the QA needs — is yours to fix too, using the target repo's
   own scripts. Re-run the failing step and watch it go green before you answer anything.

4. **Prove the pid still serves the dir**: `control --run <dir> status`.

5. **Reload**: `control --run <dir> reload` (`--core` only for a `switch-cli`).

6. **Answer**, with the path step 1 printed:

   ```bash
   workhorse-<workflow> control --run <abs run_dir> answer --gate <path from step 1>
   ```

   The run refuses a path it is not waiting on, and a non-confirmed answer exits 1 —
   so treat exit 0 as the only success.

## A dead run

Shorter, and with no socket in it: there is no process left to talk to.

1. **Read what it left.** The job carries `failure_class` and `node` from the run's own
   `kind="failure"` handoff entry — machine-readable, so route on it directly rather than
   parsing prose. A run killed outright leaves no entry; then start from
   `checkpoint.json` and `events.jsonl` instead.

2. **Investigate** from the paths the handoff names (`checkpoint`, `turns`, and every
   artifact the raise site attached).

3. **Patch and verify**, exactly as step 3 above — and with the same refusal: a failing
   gate ends the attempt with a diagnosis in `inbox.jsonl` and the run left dead.

4. **Resume it in place**, the one canonical spelling:

   ```bash
   workhorse-<workflow> run --resume-run <abs run_dir>
   ```

   Never replay the original launch argv. Doing so is actively destructive: `--no-cache`
   deletes the run dir the resume exists to save, and a stale `--param` file beats the
   checkpoint.

## When you cannot diagnose or fix it

Say so, in the run's `inbox.jsonl`, naming what you read and what you ruled out — and
leave the gate armed or the run dead. That outcome is a pass, not a miss: the next
attendant, or the operator, starts from your notes instead of from the beginning.
