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

The workflows under test are given that backlog and a greenfield repo, in three phases:
`genesis` (the `coder` workflow's greenfield flow — `workhorse run coder genesis`), then
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

## Iterating on a workflow (`evals.py`) — designed, not built

> **Status: not implemented.** `evals.py`, `evals/<workflow>.yml` and the fixture store do
> not exist in this tree; only `.gitignore` entries for their output do. What follows is the
> design the harness is meant to satisfy, kept here because the constraints are the hard
> part and they are settled. `bench.py` above is the harness that *does* exist.

`bench.py` answers *is the workflow good?* — once, over hours, as a single sample. That
makes it a regression gate and a poor instrument: a prompt edit worth 15 points of node
success rate is invisible in one end-to-end run, and one lucky run "proves" a change that
did nothing.

`evals.py` would measure the other way round: **one node, many samples, frozen input.**

```bash
evals.py harvest --run ~/runs/author-default   # freeze real node entries as fixtures
evals.py list                                  # what's in the store
evals.py run --node write_story                # baseline pass rate
evals.py compare --node write_story --b candidate-prompt.md
```

Three pieces, all data:

- **fixture** — the exact context a node was entered with in a real run, plus the repo
  commit it read. Harvested from run artifacts, never hand-written, so the distribution
  is the real one.
- **variant** — the change under test, as an *overlay on the workflow package*: a bare
  file replaces the node's prompt, a directory is mirrored over the whole workflow. So an
  edit to the state machine itself, or a stricter validator, is as testable as a reworded
  prompt — which matters, because those are the **stronger** fixes and the tooling should
  not make the weakest one the easiest to try.
- **grader** — the workflow's *own* deterministic gate, named by node id in
  `evals/<workflow>.yml`. `write_story` is graded by `validate_story` and
  `check_story_grounding`, the same two scripts production runs. Not a rubric, not a
  judge: tightening `validate_story` tightens the eval in the same commit, and the two
  can never drift into different opinions of "done".

### What makes the number trustworthy

- **A defaulted output is a failure.** Replay sets `use_default_outputs=False`, so the
  fail-soft ladder that keeps unattended runs alive cannot quietly score as a pass.
- **The verdict needs two bars.** A change is accepted only when a paired randomization
  test clears `--alpha` *and* the mean per-fixture gain clears `--min-effect` (10 points
  by default). Significance alone is buyable with sample count.
- **Fixtures are split tune/holdout** (deterministically, by id hash). The tune split has
  to show the gain; the holdout only has to not contradict it. Requiring significance
  twice on a small store would reject every real improvement.
- **Too many harness errors means no verdict.** Above 20% crashed samples the run isn't a
  measurement, and it says so instead of printing a number.
- **Replay never touches the harvested repo.** Each sample gets a `git worktree` at the
  fixture's commit and every path in the context is rebased into it.

### Limits worth knowing before you trust a result

- **Graders check well-formedness, not quality.** A prompt can be tuned to satisfy
  `section_gaps` while writing worse stories. That is what `bench.py score`'s judged
  backlog satisfaction is for — iterate here, gate there.
- **Only a node's last visit is harvestable.** `context_after.json` is overwritten per
  visit, so a node that looped eleven times yields one fixture. Breadth comes from more
  runs, not deeper mining of one.
- **Fixtures carry real run content**, so the store (`.fixtures/`) is gitignored and
  `$STABLEMATE_EVAL_FIXTURES` moves it off the tree entirely when harvesting from a
  private repo. This directory ships publicly — see the root `CLAUDE.md`.

### Adding a node

Declare it in `evals/<workflow>.yml` with the downstream script node that grades it. A
node qualifies when its input is recoverable from artifacts, its output is graded by a
deterministic node *in the same graph*, and failing that gate is a real defect. If a node
has no deterministic gate, add one to the workflow first — that fix is stronger than
anything the eval would have measured.

## Adding a benchmark app

Nothing in `bench.py` knows about todo-app. Copy `todo-app/bench.yml`, point it at a new
target and backlog, and run `bench.py --spec path/to/bench.yml score`. The layout:

```
bench.py              the end-to-end harness: one score for the whole workflow chain
evals.py              the node-replay harness: A/B one change, many samples   (PLANNED)
evals/author.yml      which author nodes are evaluable, and what grades each  (PLANNED)
rubric.md             the judge's prompt — the file to tune when scores feel wrong
tests/                the properties the score rests on
todo-app/
  bench.yml           the app: target, backlog, surfaces, repo gates
  docs/backlog.md     the pristine input, copied into the target on every run
  .runs/              logs, run artifacts, scorecard.json  (gitignored)
.fixtures/            harvested node inputs                (gitignored — real run content)
.evals/               eval results and per-sample run dirs (gitignored)
```

The backlog is **copied, never generated**, so every run starts from the same bullets and
the outcome is attributable to the workflows rather than to input that drifted.
