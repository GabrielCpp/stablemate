# The task API

`from paddock import Score, score, step, task` is the whole public surface a tasks module
needs. The helpers under `paddock.tasks` are the rest of it.

## Declaring tasks

- `task(name=, config=None, inputs=None)` opens a task. Call it several times in one
  module to declare several tasks. A repeated name is an error.
- `@step()` and `@score()` bind to the most recently opened task. Steps run in
  declaration order. A task with no `@score()` is unscored, and its output waits for
  whoever drives the session to read it.
- `inputs` values are str, number, bool or a list of str. Read them with
  `paddock.tasks.inputs.names`, `number` and `flag`, which type-check and default.
- `config` is a partial home config. A model swap is a config override, because the
  harness has no model vocabulary of its own. A merge can add and replace keys. It cannot
  delete a key the base file sets, so keep the base minimal.
- `Score(headline=, detail=(), data={}, caveats=())` is what a score returns.
  `headline` is the one line a comparison reads. `data` is the machine-readable rest.

## The `run` handle

| Attribute | What it is |
|---|---|
| `run.repo`, `run.stage` | the copy of `data/` the steps mutate. `run.repo` refuses a folder of repos |
| `run.repos` | each staged repo by name, read-only. Pass one as `cwd=` to `run.cli` |
| `run.data` | the benchmark's own `data/`, read and never written |
| `run.artifacts` | this step's log directory, kept in the workspace |
| `run.workdir(name)` | a fresh directory under `scratch/`, left out of the result |
| `run.config` | the absolute path of the merged config |
| `run.cli(*argv, check=False, timeout=None, cwd=None, env=None)` | a subprocess logged into `run.artifacts` |
| `run.project` | the pinned checkout of the code under test |
| `run.inputs` | the task's declared inputs, read-only |
| `run.benchmark` | the loaded benchmark: root, name, base config, data path, tasks |
| `run.name` | benchmark, task, data commit, code commit, number |

`run.cli` sets `PWD` to the working directory and drops `OLDPWD`. An agent CLI that
finds its project root from the environment would otherwise commit into the harness.

A tree that must outlive the run gets copied into `run.artifacts` by the step.

## Files beside tasks.py

Fixtures, rubrics and answer keys sit in the benchmark folder next to `tasks.py`. A
private helper module may sit there too. The loader puts the benchmark folder on
`sys.path` only while it imports `tasks.py`, so a top-level `import helper` works and
nothing leaks into the next benchmark.

## The helpers

| Module | Reach for it to |
|---|---|
| `paddock.tasks.stablemate` (drives the workhorse CLIs) | pin the effective config (`pin_config`), render the agents layer into the stage (`install_agents`), build the `uv run` prefix for the pinned checkout (`uv_run`), point a trial at its own artifacts dir (`trial_env`, `spec_dir`), and fail the round on a toolchain leak (`no_leaks`) |
| `paddock.tasks.frozenapp` | materialize a story's tree, seed a defect from an answer key, run QA on it, and score detection |
| `paddock.tasks.mutants` | seed a curated behavior change and score the pin rate |
| `paddock.tasks.replay` | replay one lane of the coder workflow cold, on a tree that already ran it |
| `paddock.tasks.greenfield` | build a repo from an approved milestone, then judge each journey |
| `paddock.tasks.tree` | the shared shape of a trial tree that is one repo or a folder of repos: its members, workspace, config and docs home |
| `paddock.tasks.forensics` | read nodes entered, repair loops, churn, hangs, cap waits and cost back off a run dir |
| `paddock.tasks.leverage` | measure how far a QA plan used what the book documents |
| `paddock.tasks.judge` | run one agent turn that waits out usage caps, and fill a rubric |
| `paddock.tasks.operator_gates` | watch for a gate nothing answered and park the round on it |
| `paddock.tasks.inputs` | typed reads of the task's inputs |

`frozenapp`, `mutants`, `replay` and `greenfield` are ready-made rounds for the shipped
workhorse coder and author workflows. Write plain steps for a workflow of your own.

The round modules expose a `Fixture` plus `run_round(run, fixture)` and
`score_round(run, fixture)`. A task built on one is a fixture declaration and two
one-line functions. Read the module's docstrings for the fixture fields.

A benchmark whose stage needs the agents layer calls `install_agents(run)` as its own
step, before any step that runs a workflow. It installs into each staged repo that has an `agents.yml`.

The frozen-app, mutant, replay and greenfield helpers accept a folder of repos as well as one repo. In a folder every trial path starts with the member name. A folder benchmark keeps its stories in the answer-key dir beside `defects.yml`. A replay `Pin` names commits per member as `{member: sha}`, and a member left out is cloned at its staged HEAD. A greenfield `Surface` names its member with `repo=`.
