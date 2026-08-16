# Comparing model sets (`matrix.py`)

`bench.py` scores one configuration; `matrix.py` runs it once per configuration and diffs
each result against a frozen Claude Code reference. This document is the sweep in full — how
a set is defined and overlaid, why the judge and the gold reference are pinned, where the
results land, and how to read the per-bullet report. The short version, and everything about
scoring a single configuration, is in [README.md](../README.md).

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

## A set is not a model

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

## The judge is pinned, and that is load-bearing

Levels 2 and 3 are behavioral claims made by an agent reading the repo, so the judge is a
measuring instrument. It used to be built from `get_backend()`, which falls back to
`$AGENT_CLI` — meaning it would have switched backends in step with the set it was
grading. Every set would have been scored by a different grader and no delta would have
carried information about either. `judge:` in `sets.yml` now outranks the ambient value
and applies to every set including gold, and is recorded in each manifest so a score that
moved *because the judge changed* can be told apart from one that moved because a model
did.

## Gold is frozen, not re-run

Two Claude Code runs over one backlog do not produce the same repo. A reference that moves
would mix its own run-to-run variance into every delta, so gold is produced once per task,
bundled, and stamped with the workflow sha, backlog hash and judge it ran under. A matrix
against a different one is **refused**, not warned about:

```
error: gold for 'link-shortener' ran on workflow 9c1058c, HEAD is 4b2e991
       — re-run: matrix.py gold --task link-shortener
```

## Where the results go

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

## Reading the report

The headline percentage is reported but is not the interesting column. Two sets can tie at
55% having failed on disjoint bullets, and *which* bullets a configuration drops is what
distinguishes a reasoning weakness from a tool-use one. So the report is per bullet:

```
| bullet          | gold | local-mixed | hosted-cheap |
| `link-create`   |    3 |      3      |     2 (-1)   |
| `link-redirect` |    3 |    2 (-1)   |     3        |
```
