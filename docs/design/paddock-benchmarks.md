# Paddock benchmarks outside the repo

**Disclosure.** I wrote this note after reading the existing solution: the `paddock` package
(runner, project pin, reaper, sandbox, seeds, pointers, archive), its README, the task modules and
helper modules under `paddock/data/tasks/`, the result pointers under `paddock/data/results/`, and
the home config schema in `core`. The design decisions they carry are claims in section 1b. I
checked each part and concept against "would I have named this without having seen the solution?"
Where a name survives from the code, section 5 says why.

## 1. Problem

The maintainer wants to know whether the coder and QA workflows finish a work-shaped story
unattended, and whether a change to stablemate made that better or worse. The evidence is a run
of a workflow against a frozen repository, scored by a rule the maintainer wrote once. The
repository that stands in for work is private, the agent config that drives it holds a chosen
model and profile, and both change on their own schedule.

Today the frozen repositories are zips the public repo cannot carry, so the repo carries a
pointer, a digest, a fetch step and a freshness test instead. The task modules that drive them
live in the public repo as scripts under a data directory, and the shared code they lean on lives
beside them as underscore-prefixed modules nothing imports except those scripts. A run is named
by a label the maintainer types, so two runs of the same task against two stablemate commits are
told apart only by memory. A `--param` flag lets a run change what the task does, so a result on
disk does not say which variant produced it.

The new shape: benchmarks live under one local root the home config names. Each benchmark is a
folder holding the repository it measures, the home config a run uses in place of the
maintainer's, and the Python module that declares its tasks. The public repo keeps the engine,
the task authoring library, and one small benchmark its tests build. A run is named by the
benchmark, the task, the data commit and the stablemate commit, and nothing else.

Who feels this: the maintainer, when a story's score moves and they cannot say whether the
workflow, the model or the fixture moved it.

## 1b. Claims

Claims from the existing solution, each re-derived or dropped below.

- C1. A seed is a zip of a repository with its `.git`, restored exactly. Re-derived as "the
  benchmark's `data/` is a git repository, copied to the workspace at a named commit". Zips go.
- C2. A result is a zip of the after-state plus a tracked pointer. Dropped. A result is a folder
  under the benchmark root. Nothing about it is tracked in the public repo.
- C3. The project a run drives is pinned to one git state, has no remotes, and a round that
  escapes the pin is reported. Kept whole.
- C4. Processes a round leaves running in its stage are found and killed. Kept whole.
- C5. The stablemate tools run inside a container image built from the checkout. Kept whole.
- C6. Scoring reads the stage and may not write it, checked by a stat manifest. Kept whole.
- C7. A task is a module declaring `task(name, seed, config)`, `@step()` functions and an optional
  `score(run)`. Kept, with `seed` replaced by the benchmark's data and `config` by an override
  of the benchmark's base config.
- C8. A run takes `--param KEY=VALUE`. Dropped. What a task does is a property of the task.
- C9. The helper modules under `data/tasks/_*.py` are task-private. Dropped. They are the task
  authoring library and belong in the package, imported by name.

## 2. Parts and concepts

### Level 1: parts

- **Benchmark root.** A directory outside any repo, named by the home config. Holds every
  benchmark, every workspace and every result. Nothing in it is public.
- **Benchmark.** One folder under `gold/`: the repository under measurement, the base home
  config, and the tasks module. The unit the maintainer adds, edits and deletes.
- **Engine.** The `paddock` package: loads a benchmark, copies its data, pins it, runs the task's
  steps, reaps, scores read-only, and writes the result folder.
- **Task authoring library.** The public functions a tasks module calls to drive a stablemate
  checkout, run a workflow, rewind a fixture, read run forensics or call a judge. Part of the
  package, with a README line per module.

### Level 2: concepts

Benchmark root layout:

```
<paddock_dir>/
  gold/<benchmark>/
    home-config.toml        base home config for every task of this benchmark
    tasks.py                the tasks this benchmark declares
    data/                   a git repository, the seed
  workspace/<benchmark>/<task>/<data commit>-<stablemate sha>/<n>/
    stage/                  the copy of data/ the run drives, pinned
    scratch/                everything else a run writes
  results/<benchmark>/<task>/<data commit>-<stablemate sha>/<n>/
    ledger.json             steps, wall time, exit codes, escapes
    score.json              what score() returned
    config.toml             the effective home config the run used
    stage/                  the after-state, read-only
```

- **`paddock_dir`.** A home config key beside `artifacts_dir`, with its `write_paddock_dir`
  writer. Default under the platform data dir. Never inside `artifacts_dir`: that root has a
  fixed set of folders and the benchmarks are not artifacts of a run.
- **Base config.** The benchmark's `home-config.toml`. A run passes it to every stablemate
  command through `--config`, so the maintainer's own config is never read. It names the
  library, the clis and the profiles the benchmark expects.
- **Config override.** A task may declare a mapping that is laid over the base config: a model,
  a profile, a cli. The engine writes the merged file to the workspace and that is the config the
  run sees. The override is part of the task's declaration, so it is part of the task's identity.
  There is no run-time flag that changes it.
- **Task.** A named declaration in `tasks.py`: steps, an optional score, an optional config
  override, and any fixed inputs the steps read. A narrower or differently tuned variant is a
  second task with its own name. Two tasks may share every step function and differ in one
  field.
- **Run name.** `<benchmark>/<task>/<data commit>-<stablemate sha>/<n>`. The data commit is the
  HEAD of `data/` when copied. The stablemate sha is the checkout the engine imports from. `n`
  counts repeats of the same name. A task's hash is not in the name: the task's name is its
  identity, and the stablemate sha fixes the engine, so a change to `tasks.py` is a change to the
  benchmark the maintainer committed in `data/`'s sibling, not a new axis.
- **Result.** A folder, not a zip. The zip only kept nested `.git` directories out of the
  maintainer's editor while results sat inside the stablemate checkout. Outside it, a folder is
  enough, and a diff against `data/` at the data commit answers "what did the run change" without
  unpacking.
- **Smoke benchmark.** One benchmark the test suite builds in a temporary root: a two-file
  repository, a base config pointing at the test's library, a `tasks.py` with one step and one
  score. It is the only benchmark the public repo knows.

## 3. Invariants

- I1. Nothing under `<paddock_dir>` is tracked by the public repo, and nothing in the public repo
  names a private benchmark.
- I2. A run reads the maintainer's home config exactly once: to find `paddock_dir`. Every
  stablemate command inside the run gets the merged benchmark config through `--config`.
- I3. A run's name determines what it measured. Two runs with the same name differ only by `n`
  and by what the agent did.
- I4. The stage has no remotes and one pinned commit; an escape is in the ledger (C3).
- I5. No process outlives its run (C4).
- I6. Scoring does not write the stage (C6).
- I7. A task's steps receive the task they belong to and nothing typed on the command line.

## 4. Forces and patterns

### Forces

- F1. The repo is public; the benchmarks are private. The seam has to be a directory boundary,
  not a `.gitignore` line, because a pointer or a digest already leaks the name.
- F2. A score has to be attributable: workflow change, model change, or fixture change.
- F3. A benchmark is edited in place as the maintainer learns; its data has its own git history.
- F4. The tasks module is Python the maintainer writes often, so what it calls must be typed,
  linted and tested like the package.
- F5. Runs are long and expensive; a result must survive without the run that wrote it.

### Between parts

- F1 → **benchmark root named by config**. The public repo holds the engine and a path key.
- F2 → **run name from the axes that move**: data commit, stablemate sha, task. Config rides in
  the task, so a model swap is a task the name shows.
- F4 → **library in the package**. `from paddock.tasks import stablemate, replay, judge` replaces
  a sibling `_stablemate.py` import that only worked because the loader put the data dir on
  `sys.path`. The relation is the one workhorse has to a workflow: the package is the public API a
  benchmark's `tasks.py` builds on, and the benchmark is the private distribution.

### Inside a part

- F3 → **data is a git repo, copied at HEAD**, with the commit recorded. No zip, no digest, no
  freshness test: git is the digest.
- F5 → **result is a folder with the effective config beside the score**. The run can be re-read
  with no engine.
- C7 + the user's constraint → **task owns its config override**. A task that wants another model
  declares it; the base config is the benchmark's. The CLI takes a benchmark and a task name, and
  no `--param`.

### SOLID check

The engine depends on a `Benchmark` it is handed, not on where it came from. The loader is the
only module that knows the folder layout under `gold/`. The task authoring library depends on the
engine's `Run`, not the reverse. Adding a benchmark touches no Python in the public repo.

### Open lookups

- Whether `core` already reads a `--config` path everywhere a run would need it, or some tool
  reads the platform default directly. A tool that ignores `--config` breaks I2.
- Whether the sandbox image needs the benchmark root mounted, or only the workspace.

## 5. Mapping onto the existing system

### Parts

| Part | Today | After |
| --- | --- | --- |
| Benchmark root | `paddock/data/` in the repo plus `~/.local/share/stablemate/paddock/work` | `<paddock_dir>` with `gold/`, `workspace/`, `results/` |
| Benchmark | a seed pointer, a config toml and a task module in three folders | one folder under `gold/` |
| Engine | `paddock/paddock/` | same package, half the modules |
| Library | `paddock/data/tasks/_*.py`, ten modules, 3139 lines | `paddock/paddock/tasks/` as public modules |

### Concepts, module by module

Kept whole: `project.py` (pin, fence, `escaped`, release), `reap.py`, `sandbox.py`,
`runner.py`'s step loop, ledger, read-only `_score` and seal, `registry.py`'s `task`, `step`,
`collect`.

Changed: `registry.task` loses `seed`, and `config` becomes an optional override mapping.
`loader.py` loads one `tasks.py` from a benchmark folder instead of globbing a data dir and no
longer puts anything on `sys.path`. `paths.py` is replaced by the benchmark root layout.
`cli.py` loses `capture`, `unpack`, `fetch` and `--param`; `run` takes `<benchmark> <task>`;
`list` walks `gold/`. `runner.execute` copies `data/` instead of restoring a zip, records the data
commit, and writes a result folder instead of a zip and a pointer.

Deleted: `seeds.py`, `pointer.py`, `archive.py`, the seed-freshness test, every pointer under
`data/seeds/` and `data/results/`, every module under `data/tasks/`, every config under
`data/configs/`. The data moves into private benchmarks the maintainer builds once from the
current seeds; that move is not this repo's work.

Moved: `_stablemate.py` → `paddock/tasks/stablemate.py` (checkout, `uv_run`, `pin_config` now
reads the merged config, `trial_env`, `spec_dir`); `_replay.py`, `_greenfield.py`, `_forensics.py`,
`_judge.py`, `_operator_gates.py`, `_mutants.py`, `_leverage.py` likewise. `_frozenapp.py` is
absorbed: what it did was unpack a seed app, which the engine now does. `_linkshort.py` is one
benchmark's probe, so it goes to that benchmark's `tasks.py`.

### What the existing system has that the design lacks

- `--param` and the label. Both are dropped on purpose (C8).
- A result zip that can be mailed. A folder can be tarred by hand when that is wanted.

## 5b. What must not move

- The pin and the escape detector, byte for byte. They are the reason a result is trusted.
- The reaper's cwd-under-stage rule.
- The read-only scoring manifest.
- `task` and `step` as the task author's vocabulary.

## 6. Slices

1. **Config key.** `paddock_dir` in `core` with its writer and default; `make vendor`.
2. **Benchmark loader and run name.** Load `gold/<benchmark>/{home-config.toml,tasks.py,data/}`,
   merge a task's override, copy `data/` to the workspace at HEAD, pin it, name the run. The
   smoke benchmark and its tests land here. `run` and `list` on the CLI switch to the new shape.
3. **Result folder.** Replace seal-to-zip with the result folder; delete `archive.py`,
   `pointer.py`, `seeds.py`, the pointers and the freshness test.
4. **Library into the package.** Move `_*.py` to `paddock/tasks/`, type and lint them to the
   repo bar, add their README lines, delete `data/`.
5. **Maintainer's benchmarks.** Outside the repo: build each from the current seeds and configs.

Slices 1 to 4 each leave `make lint` and the paddock tests green. Slice 2 is the walking
skeleton: after it a run of the smoke benchmark produces a named, pinned, scored result.

## 7. Assumptions

- A1. Every stablemate tool a run drives honours `--config` (open lookup above).
- A2. The maintainer rebuilds the private benchmarks from the current seed zips by hand; no
  migration command is wanted in the public repo.
- A3. A result the maintainer wants to keep forever is copied out of `results/` by hand; the
  engine never deletes one.
- A4. The sandbox mounts `<paddock_dir>/workspace/<run>` and the merged config, not the whole
  benchmark root.
