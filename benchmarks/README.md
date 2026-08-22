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
bench.py design-score  # did author DESIGN the app, or transcribe the brief?
bench.py reset      # delete the target and start clean
```

Phases are separately invocable because they have wildly different costs. Useful flags:
`--no-judge`, `--jobs N`, `--bullet <id>` (repeatable, to re-score one bullet while tuning
the rubric).

## The grill gate, and why the harness answers it the way it does

`author` opens with a grill: it briefs the operator on what the backlog leaves open and
then blocks on `docs/epics/_author-context.md`, unconditionally — `operator_mode` does not
gate it, because the premise is that those decisions belong to a person. A benchmark has no
person. Without a standing answer, every suite's `author` phase parks until its budget
expires and nothing is ever scored.

So `bench.py author` runs a watcher beside the phase that stamps that one gate answered,
with the text below the rule in [`grill-answers.md`](grill-answers.md) (per-suite override:
`grill:` in the spec). Two properties matter more than the mechanism:

- **It answers only the grill.** Every other block reached an operator because the
  resolver could not ground it in something already written, and a canned answer to one of
  those is a give-up wearing an answer's clothes. Those park, and the escalation shows up
  in the reliability half of the scorecard where it belongs.
- **It settles nothing the backlog had not.** The answer hands every open question back as
  a design decision. For a `design:` suite this is not a stylistic choice: a grill asks
  precisely the questions whose answers are the thing being measured — the run above asked
  outright whether locale switching is per-person or a switcher on the page — so an
  operator who answers helpfully has told the workflow what to design, and every design
  score after that measures transcription. A test asserts the shipped answer names none of
  the shipped expectations.

## `design-score`: measuring what the brief implied and author never wrote

`score` measures **backlog satisfaction** — every bullet the workflow was handed, judged
against the repo. It is blind, *by construction*, to the failure that motivates this
command.

A real authoring run produced a backlog-satisfying plan for an app a person could not
operate: no way to sign out, no way to delete a page, screens reachable only by typing a
URL, a promised second locale nobody could switch to, labels that disagreed screen to
screen. None of those was ever a bullet, so satisfying every bullet said nothing about
them, and the scorecard scored the run fine. Authoring an app from a brief is a **design**
act, and nothing measured whether author designed.

```bash
uv run python benchmarks/bench.py --spec benchmarks/suites/docs-app/benchmark.yaml design-score
```

**The invariant the whole metric rests on: a design-completeness score is judged against
expectations the workflow under test was never shown.** The measurement *is* the gap
between what a brief implies and what author wrote, so the moment the expectation list —
or a paraphrase of it — reaches the backlog, a prompt, an installed skill the run
resolves, or anything else a phase reads, the benchmark stops measuring design and starts
measuring transcription. Silently: the scores keep printing. So the expectations live
under `suites/<name>/hidden/`, which nothing copies into the sandbox, and the suite's
`backlog.md` is *deliberately underspecified* — that is its job, not a defect to fix.

This is the same discipline `bench.py` already applies one level down: planning documents
are claims, not evidence. Here the input backlog itself is the claim about scope, and the
hidden pack is the evidence standard.

### What it scores

Each held-out expectation is an **invariant** plus a **rendering**. The invariant is the
type-independent symmetry — "every entered state is exitable" covers a logout button today
and a close-connection call in a future `http-api` suite; the rendering is what that means
for an app of this shape, and the rendering is what the judge scores. That split is what
lets the suite family grow to other app classes without a new rubric language each time.

A judge reads **only the authored epics and stories** — no coder run required — and
assigns:

| level | name | means |
|---|---|---|
| 0 | `absent` | no epic or story acknowledges this expectation |
| 1 | `mentioned` | prose refers to it; no story's acceptance criteria would deliver it |
| 2 | `covered` | a story's acceptance criteria, taken literally, deliver it |

**Design satisfaction** is the mean as a percentage of 2. The honesty mechanics are
`score`'s, unchanged and one notch stricter: every level ≥1 must cite a planning document
that exists, an epic's own claim of completeness lifts nothing, and a citation of
*implementation code* is refused outright on the paper run — it proves the coder shipped
something and proves nothing about what author wrote. An unverifiable claim scores
`absent` rather than being discounted, because unlike in `score` there is no structural
fact underneath it to fall back on.

Author-only is the point, and it is the `link-shortener` lesson: a benchmark you can only
afford daily gets consulted daily. Author on a five-bullet brief costs tens of minutes,
which is the budget at which a design-stage fix gets a same-session verdict — and it
isolates the variable, since a coder failure cannot masquerade as an authoring one.

### The two lenses beside the number

**Dead ends per journey.** A fixed list catches what someone thought to list; the observed
misses also included incoherence no enumeration holds. So the suite hides two or three
persona journeys (sign in → find a page → edit → switch locale → delete a page → sign
out), and the judge walks each *on paper* through the authored stories, counting the steps
no story delivers. The grammar ports across app classes — web = clickpath, CLI = shell
session, HTTP API = client sequence, library = a consumer writing a program — and the
metric is the same everywhere.

**The entity × operation matrix.** Deterministic, free, and run first: every entity the
stories create, crossed with read/update/delete. An entity a story creates and no story
deletes is the missing-delete failure, found with no agent turn at all. It is reported
*alongside* the judged score the way reliability already is, never merged into it — it
reads verbs, so a story that delivers deletion without ever saying "delete" reads as a
gap, and averaging a heuristic into a judged number would hide both.

`--no-judge` prints the matrix and **declines to name a number**. `score --no-judge` can
still say `planned`, because the epic graph records coverage; nothing records whether
acceptance criteria would deliver an expectation nobody wrote down, so a structural design
score would be an invention.

### The anchor run

Once per author redesign — not per fix — run the full genesis→author→coder chain and score
the same expectations against the *built* app, where level 3 `operable` becomes reachable:

```bash
uv run python benchmarks/bench.py --spec benchmarks/suites/docs-app/benchmark.yaml design-score --live
```

Its only job is calibration. It writes `design-scorecard-live.json` beside the paper
`design-scorecard.json` rather than over it, and prints the two side by side. If they
diverge, the *instrument* is what is wrong, and it gets fixed before any more author work
trusts the cheap number.

### What this is not

- **Not a general quality rank.** Like `link-shortener`, one suite cannot rank a workflow;
  it can say whether a specific, historically observed failure mode recurs.
- **Not a reliability measure.** Escalations, repair loops and ACTIVE time stay in the
  reliability half — a run can escalate ten times and design a complete app.
- **Not a coder benchmark.** A `covered` story badly implemented is the coder's failure,
  and `score` already catches it. This stops at what author wrote down.

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
uv run python benchmarks/matrix.py sets                          # what is defined, and its tags
uv run python benchmarks/matrix.py gold --task link-shortener    # freeze the reference
uv run python benchmarks/matrix.py run --tag quick               # every set × the cheap tasks
uv run python benchmarks/matrix.py report --task link-shortener --write
```

A **set** is not a model: one `coder` run makes 41 agent turns across three power tiers, and
a set may point each tier at a different model on a different backend, so results are keyed
by the set's label and the tier→model mapping travels inside every scorecard. That is what
makes a single-tier ablation the natural experiment. Two things are pinned so a delta means
something — the judge (`judge:` in `sets.yml` outranks the ambient backend) and the gold
reference (produced once per task, and a matrix against a stale one is refused rather than
warned about). Cells are sequential and resumable, and land in the gitignored `data/`.

Set definition and overlay, the reasoning behind both pins, the `data/` layout and how to
read the per-bullet report are in [docs/MATRIX.md](docs/MATRIX.md).

## Iterating on a workflow (`evals.py`) — designed, not built

> **Status: not implemented.** `evals.py`, `evals/<workflow>.yml` and the fixture store do
> not exist in this tree; only `.gitignore` entries for their output do.

`bench.py` answers *is the workflow good?* once, over hours, as a single sample — a fine
regression gate and a poor instrument. `evals.py` would measure the other way round: **one
node, many samples, frozen input**, over three pieces of pure data — a *fixture* (a node's
real entry context, harvested from run artifacts), a *variant* (the change under test, as an
overlay on the workflow package, so a state-machine edit is as testable as a reworded
prompt), and a *grader* (the workflow's own deterministic gate, never a rubric).

The design — what makes the number trustworthy, the limits worth knowing before trusting a
result, and when a node qualifies — is in [docs/EVALS.md](docs/EVALS.md).

## Measuring one flow instead of the whole chain (`replay.py`)

`bench.py` moves every variable at once over hours, so it cannot attribute a difference to
the one prompt you edited. `replay.py` replays **one flow, one story** against a frozen app,
so everything else about the tree is byte-identical between trials.

```bash
replay.py run --flow qa --story expense-list -n 3 --label after   # three trials
replay.py report before                                           # the loop table for a label
replay.py --fixture seat-booking score                            # detection + convergence
```

Laps and dollars are the wrong half to optimise alone — a flow that approves everything
converges in one lap — so `score` answers *did QA catch what was actually wrong?* against an
app whose defects are known in advance ([`apps/`](apps/README.md)), and prints both numbers
together: `caught 6/8  missed 2  false 1 | plan-qa 2.1 laps ~$0.94`.

Detection is still only half of what a QA plan can get wrong, so the same line carries five
**leverage** metrics — did the plan enter each flow where the book says it starts, move
between screens by clicking rather than by re-navigating, address the UI by roles and
selectors the book vouches for, and close the obligations and journeys it owed?

```
caught 9/11  missed 2  false 0 | plan-qa 2.4 laps ~$1.31
  leverage: entry 2/3  deep-links 4  roles 11/14  obligations 12/15  journeys 1/3
```

A plan can catch every seeded defect while doing none of that, and the difference is QA
versus a regression suite of URL fetches. The two halves are reported side by side and never
merged: the rounds worth reading are the ones where they disagree.

How detection is scored off machine-readable state rather than off reading the QA report,
the verdict distinctions that keep a harness failure from arriving as a catch or a miss,
what each leverage metric counts and why a missing input prints `–` instead of `0`, where
the money figure comes from, and why the backend is pinned, are in
[docs/REPLAY.md](docs/REPLAY.md).

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
design-rubric.md      the design judge's prompt: one held-out expectation, 0-2
journey-rubric.md     the design judge's other prompt: walk a persona, count dead ends
grill-answers.md      the operator's standing answer to author's grill gate
docs/                 MATRIX.md, EVALS.md, REPLAY.md — one per harness above
tests/                the properties the score rests on
suites/               every benchmark, one directory each
  README.md           which suite catches what, and the tag vocabulary
  <name>/             the directory name IS the task name
    benchmark.yaml    the app: target, backlog, surfaces, repo gates, tags
    docs/backlog.md   the pristine input, copied into the target on every run
    hidden/           design suites only: the held-out expectations and journeys,
                      which NOTHING ever copies into the target — see its README
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
