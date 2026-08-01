# The debugging task set

Three small benchmark apps, sized so a whole `genesis → author → coder` chain finishes
inside an hour. They exist for a different job than [`todo-app`](../todo-app/bench.yml),
and the difference is the point.

`todo-app` answers *how good are these workflows* — four surfaces, eighteen bullets,
hours per run, one sample. That is the right instrument for a verdict and the wrong one
for a fix cycle: a defect in the coder's fifth node costs most of a day to reach twice,
so you get one or two observations a day and every one of them is confounded by the
dozen things that happened before it.

These answer *did the workflows get stuck, and where* — which is a question you need
answered repeatedly, cheaply, and today. They are deliberately not comparable to
`todo-app`'s score, or to each other's: a smaller backlog is an easier backlog, and the
number they produce is only meaningful against the same spec's own history.

| Spec | Surfaces | Bullets | Budget | What it is for |
|---|---|---|---|---|
| [`link-shortener`](link-shortener/bench.yml) | api (Go) | 3 | 30 min | The smoke run. Fast enough to re-run after every fix, small enough that a failure has one cause. |
| [`expense-split`](expense-split/bench.yml) | api (Go) | 5 | 60 min | The workload run. Enough stories for the coder to loop over, which is where staleness and churn actually appear. |
| [`bookmarks`](bookmarks/bench.yml) | api (Go) + web (React Router) | 4 | 60 min | The cross-surface run. Two surfaces is where story decomposition, plan-context and per-stack templating go wrong; one surface never exercises any of it. |

```bash
uv run python benchmarks/bench.py --spec benchmarks/tasks/link-shortener/bench.yml all
uv run python benchmarks/bench.py --spec benchmarks/tasks/link-shortener/bench.yml watch
```

## What makes them finish in an hour

Two spec fields that `todo-app` does not set, both new, both deliberately spec data
rather than machine state.

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

## Ports belong to the spec

**The benchmark owns `18080-18099` and nothing else.** Every surface that listens names its
port in its backlog's surface list, and no two specs share one — `expense-split` api 18080,
`link-shortener` api 18081, `bookmarks` api 18082 and web 18092. A new spec takes the next
free number in the range and writes it down the same way.

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

## Why these three, and not one

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
