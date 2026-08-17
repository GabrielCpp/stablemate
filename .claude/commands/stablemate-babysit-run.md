---
description: "Watch a run's outbox and inbox from this session — on a failure or a gate, diagnose, fix stablemate, reload the run, and resume, asking the operator only when stuck"
argument-hint: "<run-id> [runs-dir]"
metadata:
  generated_by: farrier
  source: library/prompts/stablemate/babysit-run.md
  resolve: "farrier source .claude/commands/stablemate-babysit-run.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# Babysit a run

A run that stops has nobody watching it until someone happens to run `groom status`
or read a terminal. This sets up a background poll loop, in *this* session, over one
run's outbox (the gate it may be parked on) and inbox (the diagnostic entry a
`WorkflowFailed` handoff writes, and anything else appended there) — so the operator
who is already sitting here is the one who gets asked, the moment there is something
to ask.

$ARGUMENTS

## 1. Resolve the run

```bash
workhorse-<name> inbox read --run <run-id> --all
groom status                                    # if groom is up: which runs are live
```

`<name>` is whichever workflow distribution owns this run (`coder`, `author`, …) — the
same console script `reload-runs` and `push-recovery` assume. If groom is down, read the
run dir directly: `<run-dir>/inbox.jsonl` and whichever gate file its checkpoint's
`waiting_on` names.

## 2. Start the poll loop

Use `Monitor` with an until-loop: block on a condition that becomes true when the run
has something new — an outstanding inbox message, a live gate, or the process having
exited — then wake this session. Do not poll tighter than a few seconds; nothing here is
time-critical enough to burn cycles on it.

Each invocation of this command starts one loop for one run id. Invoking it again for a
*different* run id starts a second, independent loop waking into this same session —
they stack. There is no dedicated stop command: closing the session, or killing the
loop, is enough. Re-invoking for a run id already being watched should not spawn a
duplicate loop.

## 3. On wake, diagnose

Read what changed:

```bash
workhorse-<name> inbox read --run <run-id>          # outstanding messages, incl. any failure entry
```

A `kind="failure"` message carries `failure_class`, the node it stopped at, and whatever
artifact paths the raise site attached — read those paths before guessing. A live gate
(outbox) instead means the run is waiting on a question, not failed; answer it like any
other gate, over groom's `POST /api/run/{run_id}/outbox` or `workhorse-<name> control`.

## 4. Fix `stablemate`, not the target repo

Failures at this layer are overwhelmingly workflow bugs, workhorse bugs, or a prompt
needing tuning — not the run's target-repo content being wrong. Find the cause in
`workhorse/` or `workflows/`, fix it there, and run that package's gate (`make lint` from
the repo root, plus the affected test package) before going further — the same
commit discipline as anywhere else in this repo.

## 5. Reload and resume

Once the fix is committed and pushed, reload the run in place — see the `reload-runs`
command for the full procedure (`workhorse-<name> control reload --run <run-id>
--at-boundary`). This resumes the run from its checkpoint under the fixed code; no
restart, no lost progress.

## 6. When you cannot diagnose or fix it, ask — don't decide alone

If the cause is not findable, or the fix is not obviously safe, say so to the operator
in this session and wait for a decision. A run's fate — resume, reload with a manual
workaround, or terminate — is always a deliberate call; this command closes the
"nobody decided, it just sat there" gap, it does not replace the decision with an
automatic one. Terminating a run, or discarding its checkpoint, still needs the
operator to say so explicitly.
