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
  two verbs: `parked` (the round stopped on a gate nothing answered) and `hand` (a person
  reached in). Both are warned about loudly — a round a human unstuck is not repeatable as
  it stands, and a round that parked was measured only up to the gate. There is no third
  verb for "the harness answered it": the harness never answers a gate, and
  `watch_operator_gates` in `tasks/_greenfield.py` says why at length.

## The author lane's grill gate, and the frozen operator turn

A backlog written at the level of observable behaviour deliberately leaves product
decisions open, and the author lane's grill gate parks and waits for an operator to settle
them. That gate is human by construction — it is the one gate of the author lane's twelve
with no auto-resolver — so an unattended round can never pass it, and an attended one is
answered differently each time, which means two rounds of the same task are not measuring
the same product.

The rule that settles this, and the one to reuse the next time a gate raises it: **freeze
what the design assigns to the operator; never freeze what the design assigns to the loop.**
A human turn the product reserves for humans is not part of the measured loop — it is the
fixture's environment, and every benchmark with a human in the loop must freeze that human
at a constant or it measures the human.

So the grill conversation was held **once**, for real, at fixture-authoring time, and both
halves of it are frozen under `apps/<name>/grill/`: the answered gate file, and the
checkpoint of the run that was parked on it. A round seeds them before the author phase and
resumes from there, which puts `refactor_backlog` — the state after the gate — first, with
nothing about the loop itself pre-supplied. `seed_grill_capture` in `tasks/_greenfield.py`
is the mechanism.

**A grounded score covers the loop given a completed operator turn; it says nothing about
the grill's question quality.** The question-generation turn no longer runs per round, so
its variance is excised rather than solved — which is honest only if it is said out loud,
here and anywhere the number is quoted.

The product decisions themselves live separately, as standing records under
`apps/<name>/docs/decisions/`, copied into the produced repo's `<docs-root>/decisions/`
where every lane's auto-resolver reads them. A record stands on its own — it says what *is*
decided, not "A2:" — so it answers whatever phrasing a later gate reaches it in. What used
to sit there instead, a sheet of replies applied positionally to one gate and stamped
`ANSWERED` unconditionally, is gone: the questions a gate asks are generated per round and
are not stable across rounds, so the sheet was routinely stamped over questions it had
never been written against.

## The benchmark fixtures (`apps/`)

Every benchmark names one directory under `apps/<name>/`, and two kinds of fixture live
there under one namespace: a **backlog** — the bullets, the decision records and the frozen
grill capture a greenfield task points at — and a **frozen app** with an answer key, input
to measuring QA. Which kind a fixture is is a property of the task that names it, not of the
directory it sits in, which is why they are not split into two trees.

`apps/todo-app` is the verdict benchmark: four surfaces, eighteen bullets, hours per run.
That is the right size for *is the workflow good* and the wrong size for *why did it break*
— a fix-and-rerun cycle measured in hours is a cycle nobody runs twice. The others are sized
so `author + coder` finishes inside an hour. Each isolates a failure class the others cannot
reach — see [apps/README.md](apps/README.md).

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
  _greenfield.py      the backlog→genesis→author→coder round, shared by every backlog
  _frozenapp.py       the frozen-app QA round: seed a defect, run QA, score detection
  _forensics.py       reading run artifacts: repair loops, node timing, cap-wait
  _stablemate.py      driving stablemate itself: config pinning, project worktrees
configs/              full stablemate configs a task pins, tracked
  seeds/              pointer TOMLs — a zipped repo lives in the store, never in git
apps/                 every benchmark fixture, one directory each
  README.md           which fixture catches what, and the port register
  <name>/             the directory name IS the name a task points at
    docs/backlog.md   greenfield: the pristine input, copied in on every run
    docs/decisions/   greenfield: standing records, copied to <docs-root>/decisions/
    grill/            greenfield: the frozen operator turn — answered gate + checkpoint
    defects.yml       frozen app: the answer key, beside the code and the book
rubric.md             the judge's prompt — the file to tune when scores feel wrong
docs/EVALS.md         the node-eval design                                    (PLANNED)
tests/                the properties the score rests on
results/              pointer TOMLs for sealed rounds                    (gitignored)
```
