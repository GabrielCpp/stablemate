---
name: paddock
description: "paddock: the benchmark harness for measuring your workhorse workflows on your own data. It copies a benchmark's data repo, drives the real CLIs against the copy, scores it when the task brought a ruler, and writes the run down as a result folder. Covers the benchmark root (`paddock_dir`), adding a benchmark, writing its tasks.py with the public task API (`task`, `@step`, `@score`, config override, inputs, the `paddock.tasks` helpers), running a task, reading a result's ledger, score and caveats, comparing runs by their name axes, isolating a book run in the sandbox, and cleaning up after a killed run. Load when asked to benchmark, measure or compare a workflow, add or edit a benchmark or a task, run one, read or compare a result, sandbox a book run, or when a run was killed from outside."
tags: [cli, tests, benchmark]
---

# paddock

paddock answers one question: what did this commit of the code under test do on this
data, under this config? Use it to tell whether a workflow change, a prompt change or a
model swap made your runs better or worse. Every run is a **measurement**, and
everything below protects that word. A round whose numbers belong to some other commit,
config or tree is not a measurement, and the harness says so in the ledger rather than
hiding it.

## The model

```
<paddock_dir>/
  gold/<benchmark>/{home-config.toml, tasks.py, data/}
  workspace/<benchmark>/<task>/<data commit>-<code commit>/<n>/
  results/<benchmark>/<task>/<data commit>-<code commit>/<n>/
```

- **Benchmark**: a folder under `gold/` that you write. `data/` is a git repo, the thing
  the steps work on: your app, a fixture repo, a seeded defect. When a task works across
  several repositories, `data/` is instead a folder whose children are each a git repo, and
  the stage holds each one under its own name (`run.repos["<name>"]`). `home-config.toml` is the
  base home config for every task of the benchmark, in the same format as
  `~/.config/stablemate/config.toml`.
- **Task**: what `tasks.py` declares. A name, an optional config override, inputs,
  ordered steps and an optional score. Config and inputs are properties of the task.
  Two models or two budgets are two tasks, never a command-line flag.
- **Run name axes**: data commit, code commit, number. The code commit is the HEAD of
  the git checkout paddock runs from, so paddock needs one. A run is reproducible by its
  name. Two runs with the same task and the same axes differ only by chance.
- **Result**: a plain folder holding `ledger.json`, `score.json`, the merged
  `config.toml` and the after-state `stage/`. `workspace/` and `results/` are scratch.
  Copy out by hand anything worth keeping.

`paddock_dir` is a key of the home config. With it unset the root is
`~/.local/share/stablemate/paddock`. Point it at a folder outside every repo you work
in, because each run holds full copies of its data.

## Operating a benchmark

1. **Know what is there.** `paddock list` prints one line per task under `gold/`:
   benchmark, task, steps, scored or unscored. Read the task's module docstring to learn
   what it measures before running it.
2. **Commit first.** The stage is a clone of `data/` at HEAD (of every child repo, when
   `data/` is a folder of them), and the code under test is a **pin** of its checkout at
   HEAD. Uncommitted edits in either are not in the run.
   Commit the change you mean to measure, then run.
3. **Run it.** `paddock run <benchmark> <task>`. It prints each step's outcome, the score
   and the result folder, and exits non-zero when a step failed. A real round lasts tens
   of minutes, so launch it in the background and wait on its exit. A round that was
   interrupted exits 130 and writes no result. `paddock resume <benchmark> <task> [n]`
   continues it on the sha it started on, skipping the steps and phases that finished.
4. **Read the ledger before the score.** `ledger.json` names the pinned sha, whether the
   source was dirty, each step's duration, command and exit code, and the **caveats**.
   Done means every caveat is accounted for. A `self-touched:` caveat says the round
   wrote into the pinned code, so its score describes a tree other than the sha in
   the ledger. Report that round as contaminated, never as a number.
5. **Compare along one axis.** Hold the task and the data commit, vary the code
   commit, and the difference is the code. Hold the sha and vary the task, and the
   difference is the config or the inputs. A comparison that moves two axes at once
   explains nothing.

## Writing a task

```python
"""What this task measures, in one paragraph."""
from paddock import Score, score, step, task

task(
    name="acme-qa",
    config={"profiles": {"claude": {"model": "opus"}}},
    inputs={"budget": 1200.0, "only": ["ACME-1"]},
)

@step()
def run_qa(run):
    run.cli("uv", "run", "workhorse-coder", "run", "qa",
            "--config", str(run.config), "--params", '{"story": "ACME-1"}', check=True)

@score()
def caught(run) -> Score:
    return Score(headline="caught 7/9  missed 2")
```

- Steps drive workflows through `run.cli`, a subprocess of the real CLI. The benchmark
  measures the surface an operator uses, which an in-process import would bypass.
- The config override deep-merges over `home-config.toml`, and task values win. The run
  hands the merged file to commands through `--config` and `STABLEMATE_CONFIG`. A relative
  `artifacts_dir`, and a relative path in a `[workspaces]` entry, name a folder inside the
  stage. The run drops `STABLEMATE_WORKSPACE` and `STABLEMATE_ARTIFACTS_DIR` from what it
  inherits.
- The score is read-only. paddock stat-manifests the stage before and after it, and a
  mutation fails the run.

The `run` handle, the `paddock.tasks` helpers and the rules a tasks module follows are in
[references/task-api.md](references/task-api.md). Read it before writing or editing any
`tasks.py`.

## After a run

A book run must see only its app, a round killed from outside leaves its processes
behind, and a result has a fixed anatomy. All three are in
[references/after-a-run.md](references/after-a-run.md). Read it before sandboxing a
book run, after killing `paddock run`, or when a result looks wrong.
