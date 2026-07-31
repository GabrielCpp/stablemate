---
type: flow
slug: workhorse-crash-resume
title: Crash and resume in place
---
# Crash and resume in place

The headline resilience path. [`drive`](../concepts/pyflow-driver.md) checkpoints
`(state, params)` **before** entering every state, so an unattended run that dies
mid-machine — process killed, machine reboot, an unrecovered `BackendInvocationError`, an
operator Ctrl-C — is never relaunched from scratch: re-issuing the **identical command
line** finds the stable run dir's [`checkpoint.json`](../run-artifacts.md#checkpointjson)
and re-enters the state it stopped in.

Resume is deliberately **coarse**: the checkpointed state is re-entered *from the top*, and
whatever it had already done inside itself is done again. There is no intra-state memo and
no fast-forward. What that buys is that the contract a state must satisfy is
**idempotency, not determinism** — a state may branch on a fresh read of the world, and
still resume correctly — and it is why a state should be sized around the work it can
afford to repeat.

- start: an in-progress `workhorse run <name> [<flow>]` dies after at least one checkpoint
  write, before any state returned [`Done`](../workflow-format.md#transition) — so
  [`run.json`](../run-artifacts.md#runjson)'s `terminal` is still `null`. An operator Ctrl-C
  qualifies and resumes identically: `run_pyflow`'s `KeyboardInterrupt` handler terminates
  the active agent turn, records the stop via
  [`record_interrupt`](../concepts/artifact-writer.md#record_interruptnode_id-error), prints
  the pause, and exits `130` — deliberately leaving `terminal` `null` so step 2 still sees
  an unfinished run. A `PyflowError` (exit `1`) marks the run `fail` but leaves the same dir
  on disk to be resumed explicitly once the cause is fixed.
- steps:
  1. **Re-run the exact same command** — same name, same `--run-id` or default, same
     `--runs-dir`, and none of `--resume-run` / `--resume-latest` / `--no-cache`.
     Auto-resume-in-place is the default path, not a flag.
  2. **Resolve the run dir** (`auto_resolve`) — the run id is the explicit `--run-id`, else
     a digest of `--params` (`p<sha1[:8]>`, so distinct parameters get distinct dirs and
     never collide), else `default`; that names one stable dir per `(workflow, run-id)`,
     the same directory the dead run was writing to. It is adopted as this invocation's
     resume target **unless** its `run.json` already carries a `terminal` — a finished run
     starts over rather than resuming into its own ending. `--resume-run <dir>` targets a
     dir explicitly; `--resume-latest` picks the newest unfinished one via
     `find_latest_resumable`; `--no-cache` forces a fresh dir.
  3. **Read the checkpoint back** (`read_resume`) — the state name, the `params` bound for
     it, the run's frozen `inputs`, `ctx`, the flow class name, and `waiting_on` for a run
     paused in an [`Await`](../workflow-format.md#transition). A checkpoint whose `engine`
     key is not `"pyflow"` is
     [refused by name](../concepts/pyflow-driver.md#a-checkpoint-from-the-retired-engine-is-refused-not-misread)
     rather than misread — the YAML front-end shared this runs directory, and one of its
     node ids that happened to match a state name would otherwise resume the wrong thing. A
     checkpoint naming a state the class no longer has fails loudly instead of silently
     restarting the run; `@workflow.state(aliases=[…])` is how a
     [renamed state](../concepts/pyflow-driver.md#renaming-a-state-without-stranding-a-run)
     keeps its old runs resumable.
  4. **Re-enter the machine there** — `setup()` does **not** run again; `ctx` is restored
     from the checkpoint and re-sealed, the params are coerced back into the state's
     declared types, and the driver dispatches into that state exactly as a fresh
     transition would. A param the state does not have is reported by name. The run's
     wall-clock budget (`WORKHORSE_MAX_RUNTIME_S`) is anchored to the run's **original**
     start read back from `run.json`, so a resume continues one budget rather than granting
     a fresh one every relaunch.
  5. **Walk on** — one state method per transition, checkpointing before each, until a state
     returns `Done`.
- end: the entry flow returns `Done`, `finish(terminal="terminal")` stamps
  [`run.json`](../run-artifacts.md#runjson)'s `ended_at`/`terminal`, and the process exits
  `0`. Dying again leaves the same stable dir resumable for another retry of this same
  journey; a `--dry-run` never participates, since it neither resumes nor is resumable.
- verify: `workhorse/tests/test_pyflow.py::test_a_resume_re_enters_the_checkpointed_state_without_re_running_setup`,
  `workhorse/tests/test_pyflow.py::test_a_checkpoint_naming_a_dead_state_fails_rather_than_starting_over`,
  `workhorse/tests/test_pyflow.py::test_read_resume_refuses_a_yaml_checkpoint`,
  `workhorse/tests/test_resume_auto.py::test_auto_resolve_skips_terminal_run`
