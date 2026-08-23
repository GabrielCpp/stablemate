# Detached jobs — measuring something outside an agent turn

`workhorse.job` runs one long command **outside** any agent turn, under a supervisor that
outlives the node that started it, and records what the command cost in a file the command
itself cannot write.

Reach for it when the thing you need is a *measurement* rather than a piece of work: a
benchmark, a training run, an evaluation sweep — anything whose value is a number, and
whose number is worthless if the process that produced it was killed for taking too long.

## Why not just run it in the node, or in the agent's shell

Three failure modes, all of them observed:

- **An agent turn's budget is a budget for thinking.** A command that runs past it is
  killed and the node restarts from scratch with no memory of the attempt — so the longer
  the experiment, the less likely anyone ever sees its result.
- **A process an agent backgrounds is owned by nothing.** The turn reaps its own
  grandchildren; the engine tears down a node's process tree when the node ends.
- **The turn that ran it is the turn asked to judge it.** With no durable artifact, a
  re-check re-runs the whole measurement.

A job is the other shape: `submit` returns immediately, the workflow parks on an `Await`,
and a later state reads two artifacts.

## Two artifacts, and why the split is the point

| written by | file | carries |
| --- | --- | --- |
| the supervisor | `runner.json` | `exit_code`, `peak_rss_mb`, `wall_s`, `kill_reason`, `tier`, `started_at`, `finished_at` |
| the command | your `result_file` (default `result.json`) | whatever the experiment claims it found |

The command writes what it *found*; the supervisor writes what it *cost*. A command cannot
fake the second one — so "measured and missed" (a result file, a clean exit, numbers that
did not clear the bar) is distinguishable from "produced no measurement" (no result file,
a non-zero exit or a kill) **without a model call**. That is what lets a classifier state
be deterministic, and it is why a job has two files rather than one.

Alongside them, in the same job directory:

| file | writer | why |
| --- | --- | --- |
| `manifest.json` | `submit` | what was asked for |
| `handle.json` | `submit` | pid, pgid, start time — written **before** the command launches, so a crash in between still leaves a findable job |
| `child.json` | supervisor | the command's own pgid, so a kill doesn't take the process holding the pen with it |
| `heartbeat` | supervisor | its mtime is liveness |
| `wake` | supervisor | mtime moves on finish, on kill, and at each overrun threshold |
| `stdout.log` / `stderr.log` | the command | its own output |

## The manifest

```python
from workhorse import job

handle = job.submit(
    {
        "command": ["uv", "run", "python", "bench.py", "--out", "result.json"],
        "cwd": str(repo_dir),
        "env": {"PYTHONHASHSEED": "0"},
        "memory_mb": 16_000,
        "cpus": 8,
        "estimate_s": 2_400,          # from a calibration probe, not from a feeling
        "min_containment": "premium",
        "result_file": "result.json",
        "labels": {"gate": "g3", "commit": sha},
    },
    job_dir=run_dir / "jobs" / "g3",
    logger=logger,
)
```

`command` is an **argv list, not a shell string** — a measurement is not a recipe, and a
pipeline in a string is a second program nobody declared. `labels` is opaque: the module
records it in the handle and never reads it, which is how a workflow keeps its own
vocabulary out of an engine primitive.

## Containment is tiered, and the tier is recorded with every result

A number measured under a hard kernel ceiling and a number measured under a polling loop
are not the same number. A result that does not say which one it is cannot be compared
with the next one, so the tier is chosen, checked against the manifest's floor, and
written into `runner.json`.

| tier | where | memory | CPU |
| --- | --- | --- | --- |
| `premium` | Linux with a delegated systemd user manager | `MemoryMax`, enforced by the kernel | `CPUQuota`, enforced |
| `best_effort` | other Linux | sampled kill | advisory |
| `advisory` | macOS, everything else | sampled kill | advisory |

`min_containment` defaults to `premium`. A machine that cannot meet it raises
`ContainmentUnavailable` — deliberately its own exception, because "this machine is too
weak" routes to whoever picks machines, while "that command would not start" (`JobError`)
routes to whoever wrote the command.

A Docker backend would make macOS a `premium` machine. It is documented as the shape and
not implemented; nothing in the API changes when it lands, because the tier is already a
recorded value rather than an assumption.

`RLIMIT_AS` is deliberately not used anywhere here: it bounds *address space*, not
residency, and arena-allocating numerical libraries reserve far more of it than they ever
touch — so it kills correct programs while letting a slow leak through.

## Resources are bound; time is not

**A job is never killed for running long.** A command that overshoots its estimate is
carrying information — about the code, or about the estimate — and killing it destroys
that information along with the work.

Instead the supervisor touches `wake` when elapsed time crosses `10×`, `20×`, `40×` … its
`estimate_s` (the first multiple is `overrun_first_multiple`), and whoever is watching
decides: keep going, or kill it and repair. The doubling is self-limiting — the wakeups
get rarer exactly as fast as the job gets less likely to be worth waiting for.

The thresholds are derived from the clock and the estimate alone
(`job.overrun_multiple(elapsed_s, estimate_s, first)`), so a poller and the supervisor
agree without either keeping a ledger the other has to trust. A job submitted with no
`estimate_s` has no thresholds and never reports an overrun.

## Watching one

```python
status = job.poll(job_dir)   # no model call, no subprocess of its own beyond `ps`
```

`JobStatus.state` is one of `running`, `finished`, `lost` (nothing is alive and no
`runner.json` was ever written) or `missing` (no handle — nothing was ever submitted
here). `result_ready` says whether the command's own file exists yet;
`overrun_multiple` is the largest threshold crossed so far.

A watcher that parks on the `wake` file has to **arm before it waits**:

```python
wake = job.arm(job_dir)      # drop the wakeup already consumed
status = job.poll(job_dir)   # …then read authoritative state
if status.result_ready or not status.alive or status.overrun_multiple > seen:
    ...                      # act now; do not park
else:
    ...                      # park on `wake`
```

Nothing is lost either way round: an event that landed before the delete is visible in
`poll`, and an event after it re-creates the file.

**Liveness is two facts, not one.** `kill -0` on the pgid answers "is *some* process group
by that number alive", which after a reboot and pid reuse is a different question from the
one being asked. So a job counts as alive only when the pgid answers **and** the heartbeat
is fresh.

`submit` is idempotent against a live job: a job directory whose handle is still alive is
**adopted**, not launched again. Re-entering the state that submitted a four-hour job —
which a resume does, since a resume re-enters a state from the top — must not start a
fifth hour of it.

## Stopping one

```python
result = job.kill(job_dir, reason="operator")   # returns what it cost up to that point
```

The supervisor is the one writer of `runner.json`, so `kill` asks it first (via a
`kill-request` file) and only reaps the group itself if it does not answer within
`KILL_REQUEST_GRACE_S`. Either way an artifact is left behind: a job that was stopped
still says what it cost and why it stopped.

`collect` on a job whose supervisor vanished returns `kill_reason="lost"` with no exit
code. *We do not know* is a classification; silence is not.

## What this is not

- **Not a scheduler.** One command, one directory, no queue, no dependencies.
- **Not workflow-aware.** It knows `command`, `memory_mb`, `estimate_s` — verbs, not nouns
  from one workflow's schema. The litmus test in
  [CLAUDE.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/CLAUDE.md) applies: a
  different workflow wants this unchanged.
- **Not a stack manager.** A long-lived *service* a later node talks to — a dev server, an
  emulator — is `ostler.qa.stack`'s job: it health-gates and adopts, which a measurement
  neither needs nor wants.
- **Not a console script.** The supervisor half is reached as
  `python -m workhorse.job supervise <job_dir>` and nothing but `submit` should run it. A
  name on `PATH` is an invitation to point it at a directory no `submit` prepared.
