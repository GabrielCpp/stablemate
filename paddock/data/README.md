# `paddock/data/` — what the rounds measure

How good is the output of an agent workflow? This directory answers that with one number.

```bash
uv run paddock run link-shortener --label smoke
```

This is the **tracked, versioned half of the harness** — the half `--data-dir` points at.
It holds task modules, backlogs, decision sheets, frozen apps, config TOMLs, pointer files
and the tests that keep all of it honest.

It is deliberately *not* described as "the part with no code in it". The task modules under
[`tasks/`](tasks/) are Python — they declare surfaces, scaffolds, repo gates and the pinned
judge — and [`tests/`](tests/) is Python too, asserting the properties every published
number rests on. `make -C paddock test` runs those tests and the harness's in one
invocation, because a benchmark whose scoring is wrong is worse than no benchmark: it
reports a figure nobody re-derives.

The split from [`paddock/`](../README.md) beside it is by *subject*, not by language. What a
round measures lives here; the machinery that unpacks a seed, drives the steps, stages the
result and seals it lives in the package, and its README is not repeated here. Living
beside the package rather than inside it is also what keeps this material out of every
install: `[tool.hatch.build]` names the inner `paddock` directory, so a sibling `data/`
ships in no wheel and no sdist.

What follows is what the tasks *measure*.

## The idea

A benchmark app is defined by a **backlog of user-observable bullets** — no implementation
tasks, no file lists, just things a person can do:

```markdown
- [todo-create] A person adds a todo by typing a title, and it appears in their list immediately.
```

The workflows under test are given that backlog and a greenfield repo, in three phases:
`genesis` (the `coder` workflow's greenfield flow — `workhorse-coder run genesis`), then
`author`, then `coder`. Afterwards, every bullet is scored 0–3 against what was actually built:

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

- **Citations are verified.** Every level ≥2 must cite repo-relative paths, and the task
  checks those paths exist. A bullet whose citations don't resolve is capped at `planned`
  and reported as unproven. This catches the judge's most common failure mode
  deterministically, for free.
- **Planning documents are treated as claims, not evidence.** An epic listing a bullet and
  a story stamped `QA passed` both mean the workflow *believed* it finished. The gap
  between that belief and the code is precisely what this benchmark exists to measure, so
  neither can lift a score on its own.

The judge is named in the task module (`judge_cli` / `judge_model` / `judge_effort`), not
inherited from the environment. Sameness is not the property that matters — pinning is: an
unpinned judge switches with whatever `$AGENT_CLI` holds, and two rounds graded by two
graders differ by an unknown amount of grader.

## Reliability is reported alongside, never merged in

The scorecard also prints repair-loop entries, operator-gate escalations, and per-node
ACTIVE time. These answer a different question — *did the machinery get there on its own?*
— and conflating the two is how a benchmark lies to you. A run can be clean and have built
nothing; a run can be full of repair loops and land a working app.

Three details worth knowing:

- **A repair loop is a defect, not a recovery.** The bounded loops exist so a run can
  recover, but reaching one means the deterministic path did not hold.
- **Cap-wait is never a hang.** A node sleeping on a usage cap is behaving correctly —
  workhorse waits caps out by design — so cap-wait is subtracted before any node is
  flagged, and shown separately.
- **A gate a person answered is not an unattended capture.** The operator-gate ledger has
  three verbs: `answered` (the harness injected the decision sheet), `parked` (the round
  went on without a decision) and `hand` (a person reached in). A `hand` entry is warned
  about loudly, because a round a human unstuck is not repeatable as it stands.

## The author lane's grill gate, and the decision sheet

A backlog written at the level of observable behaviour deliberately leaves product
decisions open, and the author lane's grill gate parks and waits for an operator to settle
them. That gate is human by construction, so an unattended round can never pass it — and
an attended one is answered differently each time, which means two rounds of the same task
are not measuring the same product.

`suites/<name>/docs/decisions.md` is that operator, frozen. The greenfield task injects it
at the gate, records the injection in the round's ledger, and reports the sha it applied. A
round whose grill asks something the sheet does not settle stays **parked** and is reported
parked — that is a finding about the sheet (extend it, and note the capture), never a guess
made at gate time.

## The benchmark suites (`suites/`)

Every benchmark is one suite under `suites/<name>/`, holding the backlog and the decision
sheet a task module points at. `suites/todo-app` is the verdict benchmark: four surfaces,
eighteen bullets, hours per run. That is the right size for *is the workflow good* and the
wrong size for *why did it break* — a fix-and-rerun cycle measured in hours is a cycle
nobody runs twice. The others are sized so `author + coder` finishes inside an hour. Each
isolates a failure class the others cannot reach — see [suites/README.md](suites/README.md).

The backlog is **copied, never generated**, so every run starts from the same bullets and
the outcome is attributable to the workflows rather than to input that drifted.

## Iterating on a workflow (`evals`) — designed, not built

> **Status: not implemented.** No eval harness, no `evals/<workflow>.yml` and no fixture
> store exist in this tree; only `.gitignore` entries for their output do.

A greenfield round answers *is the workflow good?* once, over hours, as a single sample — a
fine regression gate and a poor instrument. An eval would measure the other way round:
**one node, many samples, frozen input**, over three pieces of pure data — a *fixture* (a
node's real entry context, harvested from run artifacts), a *variant* (the change under
test, as an overlay on the workflow package, so a state-machine edit is as testable as a
reworded prompt), and a *grader* (the workflow's own deterministic gate, never a rubric).

The design — what makes the number trustworthy, the limits worth knowing before trusting a
result, and when a node qualifies — is in [docs/EVALS.md](docs/EVALS.md).

## The layout

```
tasks/                what a round does, one module per benchmark  (paddock loads these)
  _greenfield.py      the backlog→genesis→author→coder round, shared by every suite
  _frozenapp.py       the frozen-app QA round: seed a defect, run QA, score detection
  _forensics.py       reading run artifacts: repair loops, node timing, cap-wait
  _stablemate.py      driving stablemate itself: config pinning, project worktrees
seeds/                pointer TOMLs — a zipped repo lives in the store, never in git
configs/              full stablemate configs a task pins, tracked
apps/                 finished apps with an answer key — input to *measuring* QA
rubric.md             the judge's prompt — the file to tune when scores feel wrong
docs/EVALS.md         the node-eval design                                    (PLANNED)
tests/                the properties the score rests on
results/              pointer TOMLs for sealed rounds                    (gitignored)
suites/               every benchmark, one directory each
  README.md           which suite catches what
  <name>/             the directory name IS the task name
    docs/backlog.md   the pristine input, copied into the target on every run
    docs/decisions.md the frozen operator, injected at the author lane's grill gate
```
