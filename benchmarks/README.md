# benchmarks

How good is the output of an agent workflow? This directory answers that with one number.

```bash
uv run python benchmarks/bench.py score
```

## The idea

A benchmark app is defined by a **backlog of user-observable bullets** — no implementation
tasks, no file lists, just things a person can do:

```markdown
- [todo-create] A person adds a todo by typing a title, and it appears in their list immediately.
```

The workflows under test (`genesis` → `author` → `coder`) are given that backlog and a
greenfield repo. Afterwards, every bullet is scored 0–3 against what was actually built:

| level | name       | means                                                       |
| ----- | ---------- | ----------------------------------------------------------- |
| 0     | `absent`   | nothing in the repo claims this bullet                       |
| 1     | `planned`  | a story exists that would deliver it; no implementing code   |
| 2     | `built`    | implementing code exists on every surface the bullet implies |
| 3     | `verified` | built, and executable evidence exercises it                  |

The headline is the mean as a percentage of 3 — **backlog satisfaction**. That is the whole
score: one rubric, one number, comparable across runs and across benchmark apps.

## Why a judge

Levels 2 and 3 are behavioral claims, and no static check can make them: a working sign-up
flow and a plausible-looking stub have the same shape on disk. So an agent reads the repo
and assigns the level (one turn per bullet, ~20s each, run concurrently).

Two things keep it honest, and they matter more than the rubric wording:

- **Citations are verified.** Every level ≥2 must cite repo-relative paths, and `bench.py`
  checks those paths exist. A bullet whose citations don't resolve is capped at `planned`
  and reported as unproven. This catches the judge's most common failure mode
  deterministically, for free.
- **Planning documents are treated as claims, not evidence.** An epic listing a bullet and
  a story stamped `QA passed` both mean the workflow *believed* it finished. The gap
  between that belief and the code is precisely what this benchmark exists to measure, so
  neither can lift a score on its own.

`--no-judge` skips the agent entirely and reports the structural trace only. It will never
say `built` — that is the claim structure cannot make.

## Reliability is reported alongside, never merged in

`score` also prints repair-loop entries, operator-gate escalations, and per-node ACTIVE
time. These answer a different question — *did the machinery get there on its own?* — and
conflating the two is how a benchmark lies to you. A run can be clean and have built
nothing; a run can be full of repair loops and land a working app.

Two details worth knowing:

- **A repair loop is a defect, not a recovery.** The bounded loops exist so a run can
  recover, but reaching one means the deterministic path did not hold.
- **Cap-wait is never a hang.** A node sleeping on a usage cap is behaving correctly —
  workhorse waits caps out by design — so cap-wait is subtracted before any node is
  flagged, and shown separately.

## Commands

```bash
bench.py genesis    # create the repo + all service skeletons      (minutes)
bench.py backlog    # re-seed the pristine backlog into the target (instant)
bench.py author     # backlog.md → epics/stories                   (tens of minutes)
bench.py coder      # implement every story                        (hours)
bench.py all        # the three above, in order
bench.py status     # what exists so far
bench.py score      # the scorecard: quality + reliability
bench.py reset      # delete the target and start clean
```

Phases are separately invocable because they have wildly different costs, and idempotent by
construction — genesis keys each skeleton step on that *service's* marker file — so a failed
run is resumed by re-running the same command. Useful flags: `--no-judge`, `--jobs N`,
`--bullet <id>` (repeatable, to re-score one bullet while tuning the rubric).

## Adding a benchmark app

Nothing in `bench.py` knows about todo-app. Copy `todo-app/bench.yml`, point it at a new
target and backlog, and run `bench.py --spec path/to/bench.yml score`. The layout:

```
bench.py              the harness
rubric.md             the judge's prompt — the file to tune when scores feel wrong
tests/                the properties the score rests on
todo-app/
  bench.yml           the app: target, backlog, surfaces, repo gates
  docs/backlog.md     the pristine input, copied into the target on every run
  .runs/              logs, run artifacts, scorecard.json  (gitignored)
```

The backlog is **copied, never generated**, so every run starts from the same bullets and
the outcome is attributable to the workflows rather than to input that drifted.
