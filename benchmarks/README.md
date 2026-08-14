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
bench.py watch      # is the run alive, churning, or stalled?      (instant)
bench.py babysit    # `watch` on a timer — blocks until it matters (until it does)
bench.py score      # the scorecard: quality + reliability
bench.py reset      # delete the target and start clean
```

Phases are separately invocable because they have wildly different costs. Useful flags:
`--no-judge`, `--jobs N`, `--bullet <id>` (repeatable, to re-score one bullet while tuning
the rubric).

### Picking up an interrupted phase

The three phases recover differently, and the difference decides the command:

- **`genesis` re-runs.** It is idempotent by construction — each skeleton step is keyed on
  that *service's* marker file — so running it again re-derives where it got to.
- **`author` and `coder` resume.** Their position lives in a checkpoint, not in the target
  tree, and a bare re-run opens a *new* run directory and starts at the first node. To
  continue one, say so:

```bash
uv run python benchmarks/bench.py --spec suites/link-shortener/benchmark.yaml coder \
  --resume --budget 3600
```

`--budget` is not optional company for `--resume` when the run stopped **on its budget**.
Workhorse anchors `WORKHORSE_MAX_RUNTIME_S` to the run's original `started_at`, so the
ceiling is a *total*, not a per-attempt allowance: resume a 1200s-budget run with 1200s
again and it meets an expired deadline on its first transition check and stops having done
nothing. Pass the new total — 3600 above buys 2400 more seconds, not 3600.

`--resume` points at the newest run of that phase **that has a checkpoint**, including one
that ended on `fail`. Workhorse's own `--resume-latest` would skip that run — a `terminal`
means the run is over, which is the right default for an operator — but this harness exists
to fix the workflow a run failed on and then continue it, and that run holds hours of story
work behind its checkpoint. Naming the dir is how you say the verdict is stale.

A budget stop is a **diagnostic, not a target**. Read `watch` before raising one: the
question it answers is whether the run was progressing when the clock caught it or already
stuck, and only the first is worth more time.

## Watching a run in flight

`score` is a post-mortem. `watch` is the live instrument, and it answers the three ways a
run fails *without* failing: progress, liveness, churn.

```bash
uv run python benchmarks/bench.py --spec benchmarks/suites/link-shortener/benchmark.yaml watch
```

It **exits non-zero when something needs attention**, so it composes into a wait loop
rather than needing to be read. What it looks for:

- **Stall** — nothing written under `.runs/` for `--silence` seconds (default 900). Cap-wait
  is excluded first: a node sleeping out a usage ceiling is healthy, and `watch` says so
  instead of counting the silence against it.
- **Churn** — a *short node cycle repeating back-to-back*, not a busy node. "This node ran
  a lot" fires on every healthy multi-story run and would therefore be ignored on the one
  run where it mattered. Period is reported because the fix differs: period 1 is a node
  retrying itself (a bounded attempt count), period 2+ is a transition condition that never
  goes false (a guard).
- **Stale code** — the run's newest event predates the workflow source it ran. A verdict
  about code that no longer exists is worse than no verdict.

The `progress:` row is context, not one of the three — deliberately, and it is the row most
likely to be misread. It counts stories whose **live, uncommitted** frontmatter says done, so
it can go *down*: a story that reached `QA passed` and then failed review is rewritten to
`Review fixes applied`, and 1/3 becomes 0/3. That is the workflow working. Chase it only when
it falls with no review verdict to explain it — otherwise read the story's `## Implementation
Status` block, which names the review that demoted it.

### `babysit` — the loop that closes over it

```bash
uv run python benchmarks/bench.py --spec benchmarks/suites/link-shortener/benchmark.yaml babysit \
  --every 180 --for 3600
```

Polls `watch` and blocks until the answer changes. That is the whole value: polling by hand
costs a turn per poll *and* still misses the failure by however long the last gap was, while
a loop that blocks costs one and returns the moment something happens. Three exits, because
they call for different next moves:

| Exit | Meaning | Next |
|---|---|---|
| 0 | the run reached a terminal and nothing followed it | `score` |
| 1 | a poll found a problem, or the run stopped without deciding — the report is above it | read it, fix, resume |
| 2 | `--for` ran out with the run still open | nothing is known to be wrong; keep waiting or not |

"Over" is two different things on disk, and the loop reads both. A run that reached an end
state stamped a `terminal` in its `run.json` — that is a *verdict*. A run that ran out of
`WORKHORSE_MAX_RUNTIME_S` (or caught a Ctrl-C) stamped `interrupted_at` and left `terminal`
null — that is a *stop*, and the null is deliberate, since `terminal` is what makes a run
invisible to `--resume-latest`. A stop exits 1 with the reason and a resume command, not 0:
there is no result to `score`, but the checkpoint is good.

A finished run is only believed once it has been **seen settled twice**. `all` runs three
phases back to back, so an ended newest run is equally consistent with "the chain is over"
and "author ended a second ago and coder is about to start"; one poll apart tells those
apart and one poll does not.

The staleness row is **context here, not a fault**. Every other row is about the run in
flight; that one is about runs that already ended, is permanently true once you edit the
workflow — which fixing today's defect is — and so would end the wait on its first poll
after every fix. A live run wedged on genuinely old code is the stall check's to report.

## The benchmark suites (`suites/`)

Every benchmark is one suite under `suites/<name>/benchmark.yaml`, with its backlog beside
it. `matrix.py` calls a suite a **task** — one cell of the set × task matrix — and the two
words name the same thing from either end: `suites/bookmarks/` is the task `bookmarks`.
They are not the same size, and the size is what you select on.

`suites/todo-app` is the verdict benchmark: four surfaces, eighteen bullets, hours per run.
That is the right size for *is the workflow good* and the wrong size for *why did it break*
— a fix-and-rerun cycle measured in hours is a cycle nobody runs twice. The other three are
sized so `author + coder` finishes inside an hour, which is what makes the babysitting loop
usable. Each isolates a failure class the others cannot reach — see
[suites/README.md](suites/README.md).

Which is which is `tags:` in the spec, so a sweep asks for a *shape* rather than for names
somebody has to remember is cheap:

```bash
uv run python benchmarks/matrix.py sets              # every task and its tags
uv run python benchmarks/matrix.py run --tag quick   # the cheap ones only
```

Two spec keys make the hour a property of the spec rather than of the laptop. `todo-app`
sets neither, and declares why in `over_hour:`:

- **`power:`** — a `power.<level>.<backend>` overlay. Model choice is the largest single term
  in both wall-clock and score, so leaving it to machine config would mean the hour holds
  only on the machine it was measured on. `bench.py` reads the operator's config, overlays
  *only* `power`, and writes the result to `.runs/config.toml` for `$STABLEMATE_CONFIG`. It
  overlays rather than replaces because `load_config` deliberately does not merge — an
  explicit config that dropped `library_dir` would silently unfind the library.
- **`budget:`** — per-phase seconds, passed as `WORKHORSE_MAX_RUNTIME_S`. Workhorse checks
  its own deadline *between* transitions, so an over-budget run halts at a node boundary
  with checkpoint and artifacts intact, and resumes. That is the difference between a time
  limit and a `timeout(1)` that kills mid-node and destroys the evidence you were after.

Genesis is budgeted but not charged against the hour: it scaffolds the repo once, is
network-bound, and a fix-and-rerun cycle skips it.

## Comparing model sets (`matrix.py`)

`bench.py` scores **one** configuration. `matrix.py` runs it once per configuration and
diffs each result against a frozen Claude Code reference — which is how you answer *what
should we actually buy?* rather than *is this good?*

```bash
uv run python benchmarks/matrix.py sets                    # what is defined, and its tags
uv run python benchmarks/matrix.py gold --task link-shortener   # freeze the reference
uv run python benchmarks/matrix.py run --tag quick         # every set × the cheap tasks
uv run python benchmarks/matrix.py run                     # every set × EVERY task — days
uv run python benchmarks/matrix.py report --task link-shortener --write
```

`--task` names one task; `--tag` names a shape and takes as many as you like, narrowing
(AND) rather than widening. A bare `run` is every set × every task including `todo-app`,
which is a days-long commitment — `--tag quick` is the one to reach for first. A tag no
task carries is refused rather than run as an empty matrix, because a typo and "nothing to
do" produce the same silent second of wall clock.

### A set is not a model

One `coder` run makes 41 agent turns — 34 at `power="high"`, 12 at `medium`, 2 at `low` —
and a set may point each tier at a different model on a different backend. So "the Qwen
result" names nothing. Results are keyed by the set's **label**, and the full tier→model
mapping travels inside every scorecard and manifest. "Which model was at `high`?" is then
a question you ask of the manifests afterwards, rather than one the directory layout had
to anticipate.

That is also what makes single-tier ablations the natural experiment. `local-cheap-high`
differs from `local-mixed` in one tier, and 34 of coder's 41 turns move with it: if the
score holds, the dense model at `high` is not earning its VRAM.

```yaml
sets:
  - label: local-mixed
    cli: opencode
    power:
      high:   {opencode: {model: qwen/qwen3.6-27b, effort: high}}
      medium: {opencode: {model: qwen/qwen3.6-35b-a3b}}
      low:    {opencode: {model: qwen/qwen3-coder-30b-a3b-instruct}}
```

A set's `power` is *overlaid* on the spec's, so a task spec that pins a cheap tier for
budget reasons still loses to the set. The spec is the benchmark; the set is the
experiment.

### The judge is pinned, and that is load-bearing

Levels 2 and 3 are behavioral claims made by an agent reading the repo, so the judge is a
measuring instrument. It used to be built from `get_backend()`, which falls back to
`$AGENT_CLI` — meaning it would have switched backends in step with the set it was
grading. Every set would have been scored by a different grader and no delta would have
carried information about either. `judge:` in `sets.yml` now outranks the ambient value
and applies to every set including gold, and is recorded in each manifest so a score that
moved *because the judge changed* can be told apart from one that moved because a model
did.

### Gold is frozen, not re-run

Two Claude Code runs over one backlog do not produce the same repo. A reference that moves
would mix its own run-to-run variance into every delta, so gold is produced once per task,
bundled, and stamped with the workflow sha, backlog hash and judge it ran under. A matrix
against a different one is **refused**, not warned about:

```
error: gold for 'link-shortener' ran on workflow 9c1058c, HEAD is 4b2e991
       — re-run: matrix.py gold --task link-shortener
```

### Where the results go

`data/` at the repo root, gitignored — and `matrix.py` re-checks that at runtime, because
every cell holds a repo with its own `.git` and a nested working tree the outer repo can
see is how a produced app ends up committed into the harness that produced it. This tree
ships publicly.

```
data/
  <set-label>/<task>/
    repo/            the produced code — its own git repo
    repo.bundle      full history in one file, for archival
    .runs/           artifacts, config.toml, scorecard.json
    manifest.json    set + workflow sha + spec hash + per-phase rc and wall-clock
    matrix.log       every phase's stdout
  reports/<task>.md  per-bullet delta, every set beside gold
```

Runs are **sequential**: wall-clock is one of the outputs, and two sets running at once
contend for the same GPU or rate limit, which makes both readings fiction. Cells are
resumable — a completed cell is skipped, so a matrix that dies in hour six resumes rather
than restarts, and `--redo` is the only way to discard a result.

A cell whose `coder` phase failed is still **scored and kept**. A partial build is the
measurement that hour bought, and re-running it throws that away.

### Reading the report

The headline percentage is reported but is not the interesting column. Two sets can tie at
55% having failed on disjoint bullets, and *which* bullets a configuration drops is what
distinguishes a reasoning weakness from a tool-use one. So the report is per bullet:

```
| bullet          | gold | local-mixed | hosted-cheap |
| `link-create`   |    3 |      3      |     2 (-1)   |
| `link-redirect` |    3 |    2 (-1)   |     3        |
```

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

- **An unanswered node is a failure.** The ladder never fabricates a node's outputs — it
  stops the run instead — so the resilience that keeps unattended runs alive cannot
  quietly score as a pass.
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

## Measuring one flow instead of the whole chain (`replay.py`)

`bench.py` moves every variable at once over hours, so it cannot attribute a difference to
the one prompt you edited. `replay.py` replays **one flow, one story** against a frozen app
— `workhorse-coder run qa` / `run docs`, both first-class entry points taking a story slug —
so everything else about the tree is byte-identical between trials.

```bash
replay.py run --flow qa --story expense-list -n 3 --label after   # three trials
replay.py report before                                           # the loop table for a label
replay.py --fixture seat-booking score                            # detection + convergence
```

Trials record into groom's telemetry like any other run, and `report` reads
`groom.store.loop_convergence` — the same function behind `groom loops`. `--label` names the
configuration, which is what makes a before/after comparison a comparison.

### Convergence is half a measurement

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

## Adding a benchmark app

Nothing in `bench.py` knows about any particular app. Copy a `benchmark.yaml` into a new
`suites/<name>/`, point it at a new target and backlog, tag it, add it to `sets.yml` if the
matrix should sweep it, and run `bench.py --spec suites/<name>/benchmark.yaml score`. The
task's name is its directory name — the spec never repeats it. The layout:

```
bench.py              the end-to-end harness: one score for the whole workflow chain
matrix.py             one score per model set, each diffed against a frozen gold run
sets.yml              the sets under test, the pinned judge, gold, and the task list
replay.py             one flow, one story, against a frozen app: convergence + detection
fixtures/             what a replay trial replays: a captured bundle, or an `app:`
apps/                 finished apps with an answer key — input to *measuring* QA
evals.py              the node-replay harness: A/B one change, many samples   (PLANNED)
evals/author.yml      which author nodes are evaluable, and what grades each  (PLANNED)
rubric.md             the judge's prompt — the file to tune when scores feel wrong
tests/                the properties the score rests on
suites/               every benchmark, one directory each
  README.md           which suite catches what, and the tag vocabulary
  <name>/             the directory name IS the task name
    benchmark.yaml    the app: target, backlog, surfaces, repo gates, tags
    docs/backlog.md   the pristine input, copied into the target on every run
    .runs/            logs, run artifacts, scorecard.json  (gitignored)
.fixtures/            harvested node inputs                (gitignored — real run content)
.evals/               eval results and per-sample run dirs (gitignored)
```

`suites/benchmark.yaml`, not `tasks/bench.yml`, and both halves of that are the same
reason: `tasks/` holding short `*.yml` files is Ansible's role layout, so editors that
guess a YAML file's schema from its path lint these against one they were never going to
satisfy. Neither name is load-bearing for the harness — `bench.py` takes any `--spec` path
— but a file that arrives pre-underlined in red is one nobody reads.

The backlog is **copied, never generated**, so every run starts from the same bullets and
the outcome is attributable to the workflows rather than to input that drifted.
