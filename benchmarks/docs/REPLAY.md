# Measuring one flow instead of the whole chain (`replay.py`)

`replay.py` replays one flow over one story against a frozen app, so a before/after
comparison moves one variable instead of every variable. This document is the whole tool:
the trial loop, why convergence alone is half a measurement, how detection is scored off
machine-readable state, and the pinned-backend and `--sandbox` decisions behind it. See
[README.md](../README.md) for the benchmark harness it sits beside.

The flow is named as a first-class entry point taking a story slug — `workhorse-coder run qa`
or `run docs`.

```bash
replay.py run --flow qa --story expense-list -n 3 --label after   # three trials
replay.py report before                                           # the loop table for a label
replay.py --fixture seat-booking score                            # detection + convergence
```

Trials record into groom's telemetry like any other run, and `report` reads
`groom.store.loop_convergence` — the same function behind `groom loops`. `--label` names the
configuration, which is what makes a before/after comparison a comparison.

## Convergence is half a measurement

Laps and dollars are the wrong half to optimise alone: a flow that approves everything
converges in one lap. `score` supplies the other half — **did QA catch what was actually
wrong?** — and that needs an app whose defects are known in advance, which is what
[`apps/`](apps/README.md) is. A scored round runs a clean control plus one trial per row of
`defects.yml` and prints both numbers together:

```
caught 6/8  missed 2  false 1 | plan-qa 2.1 laps ~$0.94
```

Detection is scored off machine-readable state, not off reading the QA report: the
obligation's status in the computed evidence map, or an audit refutation citing it. Three
distinctions the verdicts keep:

- **`uncovered` is not a catch.** Nothing was asserted, so nothing was detected. It scores
  `inconclusive`, and so does a missing evidence map or an obligation this trial never owed —
  a harness failure must never arrive as either a catch or a miss.
- **A clean control that refutes is a fixture bug**, not a finding, and shows up as a false
  alarm.
- **`caught_by` is recorded, not scored.** Whether a defect surfaces from a failing scenario
  or from the auditor is the plan's choice, and the plan is the thing under measurement.
- **A repaired defect is a catch, not a miss.** QA does not only observe: it triages a
  failing observation as a code failure and fixes the product, after which the terminal
  evidence map is computed over a fixed app and correctly reads `covered`. The seeded file
  is what tells that apart from a run that never noticed — it was planted by a whole-file
  overwrite, so a trial ending with it no longer byte-equal to the variant detected the
  defect. A miss needs all three: a published pass, the obligation covered, *and* the
  defect still in place.

The money is the harness's own where it reports any, and `groom.prices`' rate card —
printed `~$2.37` — where it does not. The default backend is `opencode`, which reports a
literal `$0` over millions of tokens; a headline printing `$0.00` there would say the round
was free. `$?` means neither exists, i.e. the model has no line in `prices.toml` yet.

```bash
replay.py --fixture seat-booking score                 # the whole key, plus one control per story
replay.py --fixture seat-booking score --defect D1     # one row
replay.py --fixture seat-booking score --sandbox       # score the sandboxed configuration
```

Trials drive **`opencode`** unless `--cli` says otherwise, and the backend is recorded on
every row of the ledger. Both halves of that are deliberate: a full round is a control per
story plus a run per defect — a dozen QA flows for one number, which on the default backend
is a benchmark nobody re-runs — and a label whose trials silently inherited `$AGENT_CLI` is
not a configuration anyone can compare against. Same reasoning as `bench.py`'s pinned judge.

`--sandbox` is a workflow param threaded to `ostler qa run --sandbox`, never an environment
read — a value outside the checkpoint means a resumed trial silently measures a different
configuration.
