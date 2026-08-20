# The benchmark suites

Every benchmark is one suite: a directory holding a `benchmark.yaml` and the
`docs/backlog.md` it runs on. The directory name *is* the name — nothing inside the spec
repeats it — and the whole set is what `matrix.py` sweeps, one cell per (set, suite). The
matrix calls a suite a **task**, which is the same thing named from the other end:
`suites/bookmarks/` is `--task bookmarks`.

They are not the same size, and that is the point. `todo-app` answers *how good are these
workflows* — four surfaces, eighteen bullets, hours per run, one sample. That is the right
instrument for a verdict and the wrong one for a fix cycle: a defect in the coder's fifth
node costs most of a day to reach twice, so you get one or two observations a day and every
one of them is confounded by the dozen things that happened before it.

The other three answer *did the workflows get stuck, and where* — which is a question you
need answered repeatedly, cheaply, and today. Their scores are deliberately not comparable
to `todo-app`'s, or to each other's: a smaller backlog is an easier backlog, and the number
they produce is only meaningful against the same spec's own history.

| Spec | Surfaces | Bullets | Budget | Tags | What it is for |
|---|---|---|---|---|---|
| [`link-shortener`](link-shortener/benchmark.yaml) | api (Go) | 3 | 30 min | `quick smoke api` | The smoke run. Fast enough to re-run after every fix, small enough that a failure has one cause. |
| [`expense-split`](expense-split/benchmark.yaml) | api (Go) | 5 | 60 min | `hour workload api` | The workload run. Enough stories for the coder to loop over, which is where staleness and churn actually appear. |
| [`bookmarks`](bookmarks/benchmark.yaml) | api (Go) + web (React Router) | 4 | 60 min | `hour cross-surface api web` | The cross-surface run. Two surfaces is where story decomposition, plan-context and per-stack templating go wrong; one surface never exercises any of it. |
| [`todo-app`](todo-app/benchmark.yaml) | api + web + app + infra | 18 | none | `long full api web app infra` | The verdict run. The only score that means "how good are these workflows", and the only task that costs hours per cell. |

```bash
uv run python benchmarks/bench.py --spec benchmarks/suites/link-shortener/benchmark.yaml all
uv run python benchmarks/bench.py --spec benchmarks/suites/link-shortener/benchmark.yaml watch
```

## Selecting tasks: `tags:`

`bench.py` runs the one spec you point `--spec` at, so it never consults tags. `matrix.py`
runs *many*, and picking them by name means remembering which names are cheap — which is
how a "quick check" becomes an overnight `todo-app` run. So each spec declares what it is:

```yaml
tags: [quick, smoke, api]
```

```bash
uv run python benchmarks/matrix.py sets                   # every task and its tags
uv run python benchmarks/matrix.py run --tag quick        # the cheap ones only
uv run python benchmarks/matrix.py run --tag hour --tag web   # both tags, not either
uv run python benchmarks/matrix.py report --tag quick
```

Repeated `--tag` is **AND**, because that is what a filter reads as; OR is spelled by
running twice. A tag no task carries is an error rather than an empty selection — the two
are indistinguishable at the shell (a matrix that finishes in a second having run nothing)
and one of them is a typo.

The vocabulary is a convention, not a schema — `matrix.py` accepts whatever the specs
declare. What is in use:

| Tag | Means |
|---|---|
| `quick` | well under the hour; safe to run after every fix |
| `hour` | one full chain inside the hour |
| `long` | hours per cell — ask for it deliberately |
| `smoke` `workload` `cross-surface` `full` | what class of failure it is built to reach |
| `api` `web` `app` `infra` | the surfaces it exercises |

## What makes the hour-sized ones finish in an hour

Two spec fields that `todo-app` does not set, both deliberately spec data rather than
machine state. `todo-app` omits them on purpose and says why in its `over_hour:` — the
verdict is only meaningful at the tier you actually ship on, and a ceiling on a run that
long stops it mid-backlog and scores a repo nobody finished.

**`power:`** overlays the operator's `power.<level>.<backend>` table for these runs only.
Which model a node runs on is the largest single term in both the score and the
wall-clock, so leaving it to whatever `~/.config/stablemate/config.toml` happens to say
makes "finishes in an hour" a property of the laptop. The task specs flatten all three
tiers onto one cheap model and low effort — every node gets the same treatment, so a
slow run is the workflow's doing and not a tier map's.

The overlay is written to `.runs/config.toml` and passed as `$STABLEMATE_CONFIG`; the
operator's own config is read but never modified. It is overlaid rather than replaced
because the rest of that file is machine truth the harness cannot invent (`library_dir`,
`stablemate_dir`, the `[harness.*]` tables), and `load_config` does not merge — an
explicit `$STABLEMATE_CONFIG` means *this file and no other*.

**`budget:`** is a per-phase wall-clock ceiling, enforced by workhorse's own
`WORKHORSE_MAX_RUNTIME_S`. That matters more than it looks: the ceiling is checked
*between* states, so an over-budget run stops at a node boundary with its checkpoint and
its artifacts intact — scoreable, and resumable with `--resume-latest`. A `timeout(1)`
around the process would instead kill it mid-node and destroy the evidence you started
the run to collect.

A budget is a *diagnostic*, not a target. A run that hits its ceiling has told you
something — read `watch` before you raise it.

## The packs are derived, not chosen

Every task installs the same repo-level packs — `product-planning`, `stablemate`,
`infra` — plus its surfaces' stack packs, and `ui` alongside `react-router`/`flutter`.
That list is not taste. It is what you get by walking the author's and coder's prompts
for every `instruction_ref` / `skill_load_ref` / `find_by_tags(...)` call site and asking
which pack supplies an answer.

The reason to derive it rather than pick it: a benchmark installing fewer packs than a
real repo of the same shape is not an easier version of the benchmark, it is a
*different* one. The workflows then run against fallback prose — "(none installed —
follow `AGENTS.md`)" — and the score measures how well an agent copes with a repo nobody
ships, while the run you actually care about had the skills all along.

Two failure modes, and they are not the same size:

- **`find_by_tags` renders a fallback.** Degraded, not broken — the prompt says what to
  do instead. Before this list was derived, `find_by_tags('runbook')` matched *nothing in
  the whole library*, so all four of its call sites (`triage-qa`, `apply-review`,
  `apply-qa-fixes`, `qa-fix-item`) took the fallback on every run. `infra` is the only
  pack that answers it.
- **`skill_load_ref` names a skill that is not there.** Not degraded — the coder's
  `document_story` and `code_review` prompts do not ask what the repo has, they say "load
  this and follow it" and name `ostler-documentation` and `code-review`. Absent, the
  agent is handed a slash command or a path that does not resolve. Both skills are in the
  `stablemate` pack, which is also the only pack the benchmark uses that ships in
  `base-library/` rather than the private overlay — so a public clone resolves it.

`architecture` and `testing` are not listed anywhere and do not need to be: `go`,
`react-router`, `flutter` and `pulumi` all `includes:` them. The prompts-only packs
(`qa`, `shared-lifecycle`, `shared-docs`) are deliberately left out — a Python workflow
renders its own package-local prompts and never reads the library's, so installing them
would add commands nothing invokes. `shared-docs`'s *scaffold* is a separate thing and is
already named explicitly by `docs_scaffold:`.

Changing this list changes `spec_sha`, which is what marks a frozen gold cell stale. That
is the intended behavior — a score from before the packs resolved is not comparable to
one from after.

## Ports belong to the spec

**The benchmark owns `18080-18099` and nothing else.** Every surface that listens names its
port in its backlog's surface list, and no two specs share one — `expense-split` api 18080,
`link-shortener` api 18081, `bookmarks` api 18082 and web 18092. A new spec takes the next
free number in the range and writes it down the same way.

The frozen apps under [`benchmarks/apps/`](../apps/README.md) draw from the same range and are
registered here for the same reason, even though they are not specs: `seat-booking` 18083 and
`policy-desk` 18084. A fixture that measures QA and a suite that builds an app can easily be
running at the same moment on one machine.

This is not tidiness. A spec that starts a server without naming a port gets the language's
idiomatic default — `8080` for Go, `3000` for React Router — and those are the two most
contended ports on a developer machine. An `expense-split` run bound its QA daemon to `8080`
while an unrelated project's stack already held it, so the readiness probe
(`POST http://localhost:8080/groups`) was answered by a stranger's service. The daemon lost
the bind and the run failed loudly, which is the *good* outcome and the one we did not
choose: had our app come up first, QA would have graded a foreign API and reported a verdict
about it, with nothing in the evidence to say so. Naming the port removes the coin flip.

The backlog is the right home for it even though it is otherwise strictly
behavior-not-implementation, because the port is neither — it is a fact about the machine
the app is allowed to occupy, and the backlog is the one document every phase reads.

## Why three small ones, and not one

Each isolates a class of failure the others cannot reach.

One surface with three bullets produces one epic and a handful of stories: if that run
churns, the cause is in the single-story path, with nothing else in the frame. Five
bullets produce enough stories for the coder to *loop*, which is the only way to see the
selector re-pick, a repair loop repeat, or a run go stale mid-queue — a three-bullet run
finishes before any of those has a chance to show. Two surfaces produce stories that
span stacks, which is where the plan-context layer maps, the per-stack skill resolution
and the prompt templating all get exercised for the first time; a Go-only run resolves
one pack and proves nothing about the second.

Backlogs are written to the same contract as `todo-app`'s: user-observable behavior,
`- [kebab-id] A person …`, no implementation tasks. A bullet that names an
implementation is a bullet the author workflow cannot be judged on, because it has
already been decomposed for it.
