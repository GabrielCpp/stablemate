# `paddock/data/` — what the rounds measure

How good is the output of an agent workflow? This directory answers that with one number.

```bash
uv run paddock run link-shortener --label smoke
```

This is the **tracked, versioned half of the harness** — the half `--data-dir` points at.
It holds task modules, milestones, decision records, frozen apps, config TOMLs, pointer
files and the tests that keep all of it honest.

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

A benchmark app is defined by an **approved milestone of user journeys** — no
implementation tasks, no file lists, just things a person can do:

```markdown
### Add a todo by title

- services: web, app, api

A person adds a todo by typing a title, and it appears in their list immediately.
```

The workflows under test are given that milestone and a greenfield repo, in three phases:
`genesis` (the `coder` workflow's greenfield flow — `workhorse-coder run genesis`), then
`author` (`workhorse-author run`, which reads the one approved milestone from the repo),
then `coder`. Afterwards, every journey is scored 0–3 against what was actually built:

| level | name       | means                                                       |
| ----- | ---------- | ----------------------------------------------------------- |
| 0     | `absent`   | no epic the milestone lists claims this journey              |
| 1     | `planned`  | a story exists that would deliver it; no implementing code   |
| 2     | `built`    | implementing code exists on every surface the journey implies |
| 3     | `verified` | built, and executable evidence exercises it                  |

The headline is the mean as a percentage of 3 — **milestone satisfaction**. That is the whole
score: one rubric, one number, comparable across runs and across benchmark apps.

## Why a judge

Levels 2 and 3 are behavioral claims, and no static check can make them: a working sign-up
flow and a plausible-looking stub have the same shape on disk. So an agent reads the repo
and assigns the level (one turn per journey, ~20s each, run concurrently).

Two things keep it honest, and they matter more than the rubric wording:

- **Citations are verified.** Every level ≥2 must cite repo-relative paths, and the task
  checks those paths exist. A journey whose citations don't resolve is capped at `planned`
  and reported as unproven. This catches the judge's most common failure mode
  deterministically, for free.
- **Planning documents are treated as claims, not evidence.** An epic naming a journey and
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
  two verbs: `parked` (the round stopped on a gate nothing answered) and `hand` (a person
  reached in). Both are warned about loudly — a round a human unstuck is not repeatable as
  it stands, and a round that parked was measured only up to the gate. There is no third
  verb for "the harness answered it": the harness never answers a gate, and
  `watch_operator_gates` in `tasks/_operator_gates.py` says why at length.

## How the milestone reaches the author, and how a journey is traced back

The author reads no parameter and no file the round names: `workhorse-author run` finds
the one `status: approved` milestone under `docs/milestones/` of the repo it runs in, and
refuses to start until `ostler doctor` has no error against it. So the round makes that
true after genesis: it copies the fixture's milestone folder to
`docs/milestones/<slug>/`, copies the decision records to `docs/decisions/`, and opens an
empty book directory under `docs/services/` for every surface, because each journey's
`- services:` bullet must name a book that exists and genesis creates none. `seed_milestone`
in `tasks/_greenfield.py` is the mechanism, and
`test_every_greenfield_task_carries_an_approved_ready_milestone` proves each fixture gets
past that gate before any round spends an hour finding out.

The author's epic split writes the epics it created into the milestone's `epics`
frontmatter, and each epic restates the journeys it delivers under its own
`## User Journeys`. The trace reads both: a journey is claimed by a listed epic whose
`## User Journeys` carries a heading with the journey's slug or names its title in prose,
and an epic the milestone does not list claims nothing and is warned about. Matching is
by title because the author's prompts ask an epic to carry its milestone journeys, not to
cite them by id, so a split that paraphrases every journey scores every one of them
`absent`. That is a defect of the split worth seeing, not one the trace papers over.

The grill gate the author holds before splitting is human by construction, and a human
turn the product reserves for humans is not part of the measured loop. The rule is
**freeze what the design assigns to the operator; never freeze what the design assigns to
the loop.** So the operator's answers are frozen as a grill record under the milestone's
`grills/` folder, where the split reads them, and the product decisions behind each answer
stand on their own under `apps/<name>/docs/decisions/`, copied into the produced repo where
every lane's auto-resolver reads them. A record says what *is* decided, so it answers
whatever phrasing a later gate reaches it in. A grounded score therefore covers the loop
given a completed operator turn, and says nothing about the grill's question quality,
which is honest only if it is said anywhere the number is quoted.

## The benchmark fixtures (`apps/`)

Every benchmark names one directory under `apps/<name>/`, and two kinds of fixture live
there under one namespace: a **milestone** — the journeys, the decision records and the
grill record a greenfield task points at — and a **frozen app** with an answer key, input
to measuring QA. Which kind a fixture is is a property of the task that names it, not of the
directory it sits in, which is why they are not split into two trees.

`apps/todo-app` is the verdict benchmark: four surfaces, eighteen journeys, hours per run.
That is the right size for *is the workflow good* and the wrong size for *why did it break*
— a fix-and-rerun cycle measured in hours is a cycle nobody runs twice. The others are sized
so `author + coder` finishes inside an hour. Each isolates a failure class the others cannot
reach — see [apps/README.md](apps/README.md).

The milestone is **copied, never generated**, so every run starts from the same journeys
and the outcome is attributable to the workflows rather than to input that drifted.

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
result, and when a node qualifies — is in [EVALS.md](../docs/EVALS.md).

## The layout

```
tasks/                what a round does, one module per benchmark  (paddock loads these)
  _greenfield.py      the milestone→genesis→author→coder round, shared by every milestone
  _frozenapp.py       the frozen-app QA round: seed a defect, run QA, score detection
  _judge.py           one agent turn that waits out usage caps, and the rubric fill
  _leverage.py        how far a QA plan used the book it was handed
  _operator_gates.py  the operator-gate ledger, and the gate watcher that parks a round
  _forensics.py       reading run artifacts: repair loops, node timing, cap-wait
  _stablemate.py      driving stablemate itself: config pinning, project worktrees
configs/              full stablemate configs a task pins, tracked
  seeds/              pointer TOMLs — a zipped repo lives in the store, never in git
apps/                 every benchmark fixture, one directory each
  README.md           which fixture catches what, and the port register
  <name>/             the directory name IS the name a task points at
    docs/milestones/<slug>/
                      greenfield: the approved milestone, copied in on every run
      milestone.md    the journeys the round traces and scores
      grills/         the frozen operator turn the split reads
    docs/decisions/   greenfield: standing records, copied to <docs-root>/decisions/
    defects.yml       frozen app: the answer key, beside the code and the book
rubric.md             the judge's prompt — the file to tune when scores feel wrong
../docs/EVALS.md      the node-eval design                                    (PLANNED)
tests/                the properties the score rests on
results/              pointer TOMLs for sealed rounds                    (gitignored)
```

## Map

- `tasks/`: what each round does, one module per benchmark, plus the shared round machinery.
- `tests/`: the properties every published score rests on.
