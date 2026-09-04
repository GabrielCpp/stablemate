# `research` — an autonomous research program, one gate at a time

A **program** is one folder in a target repo: a North star with a frozen target, a ladder
of numerically-gated milestones, and a ledger. This workflow drives that ladder — it picks
the next gate, designs an experiment for it, builds it, **measures it outside any agent
turn**, judges the artifact, records the verdict, and moves on. It stops when the North
star is reached, ruled out, or banked.

From a Stablemate checkout, scaffold a program first; the workflow consumes what it
stamps:

```bash
uv run python -m workhorse_workflows.research.scaffold.new_program \
    --repo <repo> --dir specs/my-program --code-root src/mypkg \
    --ram-gb 64 --cpus 16
workhorse-research run --params '{"program": "specs/my-program"}'
```

---

## The measurement is not in the turn (load-bearing)

This is the one thing to understand about this workflow.

An agent turn's budget is a budget for *thinking*. An experiment's budget is however long
the experiment takes. When the two are the same number, the loop silently trades the
second for the first: a measurement that runs past the turn is killed with no memory of
the attempt, and a reviewer asked to re-check it re-runs "the largest subset that fits"
and records **that** as the verdict — a second, worse experiment standing in for the first.

So `submit` hands the command to `workhorse.job` (see
[`workhorse/docs/JOBS.md`](../../../../workhorse/docs/JOBS.md)), the workflow **parks on
an `Await`** for as long as it takes — hours, days, across a driver that may die and
resume — and `collect` reads two files back. Nothing that judges the result can re-run it;
`gate-check` is not even shown the command.

Time is therefore not a budget here, and no state has a timeout. A job past its estimate is
**triaged**, not killed: 10× / 20× / 40× wake the engineer, who either lets it keep going
(unbounded — a slow experiment is still an experiment) or kills it with a diagnosis, which
is the only way a job dies of time.

---

## Three personas, because three different things go wrong

The failure this split exists for: *gates fail on engineering bugs*. A loop with a
scientist and a lead and nobody who owns a traceback answers "the harness crashed" with a
protocol change, and spends its science budget on a `ModuleNotFoundError`.

| persona | power | owns |
| --- | --- | --- |
| **scientist** (`design-experiment`) | `smart` | the protocol, the declared resources, the calibration probe, and every *scientific* rework |
| **engineer** (`build-experiment`, `triage-overrun`) | `high` | whether it runs: the code, the argv handoff, the n=1 dry run, crash repair, overrun triage |
| **lead** (`gate-check`, `research-lead-review`, `lead-goal-review`) | `extra-smart` | verdicts on artifacts, whether a kill was sound, and the program's direction |

`gate-check` and `research-lead-review` are separate reviews of separate questions: the
first judges one artifact against one gate's thresholds, the second judges whether the
*gate* is still worth pursuing. `lead-goal-review` is a third node again, and it is the
only one that can end the program.

---

## The loop

```
start (select gate)
  ├─▶ design    [scientist]     protocol + declared resources + calibration probe
  ├─▶ build     [engineer]      make it runnable; bounded n=1 dry run through the runner
  ├─▶ submit    [deterministic] envelope check → bounded detached job → handle file
  ├─▶ Await(result file)        hours or days; the driver may die and resume
  │     └─ overrun 10×/20×/40× ▶ triage [engineer] ─ keep going ▶ re-Await
  │                                                 └ kill+fix  ▶ build
  ├─▶ collect   [deterministic] runner file + result.json → classify, zero model calls
  │     ├─ crash/invalid, repo fault ▶ build   (×3 → lead review)
  │     ├─ crash, tooling fault      ▶ Await(operator), immediately
  │     ├─ over-resource             ▶ design  (rescope ×2 → lead review)
  │     └─ ok                        ▶ check
  └─▶ check     [lead]          artifact vs thresholds — never re-runs the measurement
        ├─ approved ▶ record_pass ▶ start
        ├─ rework   ▶ design  (×2 → lead review)
        └─ killed   ▶ lead_review ─┬─ revive         (autonomous)
                                   └─ new_direction  ▶ Await(operator)
```

**No arm ends in `WorkflowFailed`.** Every exhausted budget is an `Await` or an escalation
to the lead; the only terminal is `record_goal`, and the only halt is at `setup()`, when a
prior run already concluded the program and nobody has re-authorized it
(`--param reauthorize=true`).

---

## Routing by fault locus

"Measured and missed" and "produced no measurement" are different failures with
different owners. Conflating them spends the scientific budget on engineering bugs
until the gate is declared scientifically exhausted.

| what happened | goes to | costs |
| --- | --- | --- |
| measured, missed the bar | the **scientist** | one rework (of 2) |
| produced no measurement, fault in this repo | the **engineer**, with no person in the loop | one build fix (of 3) |
| produced no measurement, fault in the tooling | an **operator**, immediately | nothing |
| outgrew its declared resources | the **scientist** | one rescope (of 2) |
| ran past its estimate | the **engineer** | nothing |

The locus is decided **deterministically**, by the deepest frame of the traceback: a frame
under the repo is a repo fault, a frame inside `workhorse` or `ostler` is a tooling fault.
Only where there is no stack at all may a persona declare a locus, and `"tooling"` with no
`component` named is treated as a repo fault and comes back to the engineer — because an
engineer that can route its own hard problems to a human by calling them "tooling" has
every reason to.

---

## The two contracts

Both are read by `collect`, which classifies with **zero model calls** — which is only
possible because two different writers wrote them.

- **`runner.json`**, written by the supervisor: `exit_code`, `peak_rss_mb`, `wall_s`,
  `kill_reason`, `tier`. The experiment cannot write this, which is what makes it
  trustworthy.
- **`result.json`**, written by the experiment, with a fixed core:

  ```json
  {"status": "ok", "metrics": {"<name>": 0.0}, "seeds": [0, 1, 2],
   "controls": ["scratch", "shuffled"], "n_completed": 240, "n_planned": 240}
  ```

  `metrics` carries whatever the gate's thresholds are stated in. `n_completed` /
  `n_planned` are how a partial run says it was partial instead of looking complete —
  a run that finished 40 of 240 units and exited clean is `needs_rework` whatever its
  numbers say. A missing core key is a *crash*, not a nuance.

The **calibration probe** is mandatory and enforced at `submit`: a design must have timed
some units to have an estimate at all, and an estimate with nothing behind it is refused
back to the scientist rather than launched. The **n=1 dry run** runs through the real
runner for the same reason — the argv handoff is what breaks, far more often than the code
does, and a command that only works when you type it fails there in seconds instead of
after four hours.

---

## `program.yml`

Flat keys, read by `load_program`:

| key | what it does |
| --- | --- |
| `code_root` | where experiments are written |
| `result_branch` | where the gate's work is committed and pushed |
| `progress_path` | the run's progress file |
| `goal` | one line, for the selection turn |
| `envelope_ram_gb` / `envelope_cpus` / `envelope_gpu` / `envelope_disk_gb` | the machine the experiments must fit; `0` / `none` declares no bound |
| `min_containment` | the weakest containment (`premium` / `best_effort` / `advisory`) a measurement here may be trusted under |

A design over the envelope is rescoped **by the workflow's own arithmetic**, before
anything is built — never by a person, and never by launching it and finding out.

`ledger.yml`, beside it, is the program's spend: `extensions`, `lead_reviews` and
`status`. It is written by `record_spend` and read by the *next* run, which is what makes
the caps bound a program rather than bound one run.

---

## Budgets

Every one of these caps the **resolver**, never the block: exhausting one hands the
question upward, and the run stays resumable.

| constant | value | on exhaustion |
| --- | --- | --- |
| `MAX_BUILD_FIXES` | 3 | → lead review (`max_build_fixes`) |
| `MAX_REWORKS` | 2 | → lead review (`max_reworks`) |
| `MAX_RESCOPES` | 2 | → lead review (`max_rescopes`) |
| `MAX_LEAD_REVIEWS` | 4 | → operator `Await`; answering grants exactly one more |
| `MAX_EXTENSIONS` | 6 | → operator `Await`; answering grants exactly one more |
| overrun triage | unbounded | — |

The counters travel as one frozen `Budget` in the state parameters, so a checkpoint carries
them as legible JSON an operator can edit, and a resume rebuilds the model rather than the
dict.
