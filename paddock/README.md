# paddock

The enclosure where horses are worked and evaluated. One benchmark harness. It copies a benchmark's repository, drives real CLI steps against the copy, scores the result when the task brought a ruler, and writes the run down as a folder.

```
copy the data  ->  run the steps  ->  (score it)  ->  write the result
```

[`paddock/`](paddock/README.md) is the code that does this.

## The benchmark root

The root is the `paddock_dir` key of the home config. It defaults to `~/.local/share/stablemate/paddock`. Three folders hold everything.

```
<paddock_dir>/
  gold/<benchmark>/
    home-config.toml          the base stablemate config for every task
    tasks.py                  the task and its steps
    data/                     a git repo, the thing the steps work on, or a folder of git repos when a task works across several
  workspace/<benchmark>/<task>/<data commit>-<stablemate sha>/<n>/
    stage/                    a copy of data/ at HEAD, mutated by the steps
    scratch/                  the steps' own working space
    config.toml               the merged config the run used
    artifacts/<step>/         logs, one folder per step
  results/<benchmark>/<task>/<data commit>-<stablemate sha>/<n>/
    ledger.json               steps, durations, commands, exit codes, caveats
    score.json                what the score function returned, or null
    config.toml               the merged config the run used
    stage/                    the after-state of the copy
```

A run is named by its axes. The data commit is the HEAD of `data/` when the run started, or a digest of each repo's HEAD when `data/` is a folder of repos. The stablemate sha is the HEAD of the checkout paddock was imported from. The number counts the runs that share both.

Anything the maintainer wants to keep for good is copied out of `results/` by hand.

## The nouns

**Benchmark**: a folder under `gold/` with a base config, a tasks module and a data repo.

**Task**: what `tasks.py` declares, one or several per module. A name, an optional config override, an ordered list of steps and an optional score function.

**Config**: the base `home-config.toml` with the task's override deep-merged over it. Task values win. A task with no override gets the base file byte for byte. A relative `artifacts_dir` names a folder inside the stage, so a benchmark whose data carries its own artifacts repo writes `artifacts_dir = "<repo name>"`. A relative path in a `[workspaces]` entry names a repo inside the stage too, as in `web = ["web-app", "api-service"]`. The engine writes the result into the run and hands it to every stablemate command through `--config`, and sets `STABLEMATE_CONFIG` to it in the environment of every command the run starts. A step takes nothing from the command line. The run drops `STABLEMATE_WORKSPACE` and `STABLEMATE_ARTIFACTS_DIR` from what it inherits, so the operator's own workspace and artifacts repo never reach it. A step that wants either sets it in the `env` it passes to `run.cli`.

**Result**: the folder under `results/`. It holds the ledger, the score, the config and the stage.

**Score**: a ruler the task brought. There is no harness-side judging. A task either measures itself or leaves its output for whoever drives the session to read.

## Writing a task

```python
"""What this task measures, in one paragraph."""
from paddock import Score, score, step, task

task(
    name="policy-desk-qa",
    config={"profiles": {"claude": {"model": "opus"}}},
    inputs={"budget": 1200.0, "only": ["PDSK-1"]},
)

@step()
def plant_defect(run):
    """Setup that is not a workflow invocation: overwrite a variant, bring compose up."""
    ...

@step()
def run_qa(run):
    run.cli(
        "uv", "run", "workhorse-coder", "run", "qa",
        "--config", str(run.config),
        "--params", '{"story": "PDSK-1"}',
        check=True,
    )

@score()                            # optional
def caught(run) -> Score:
    return Score(headline="caught 7/9  missed 2", data={...})
```

- `task()` opens a task and may be called several times in one module. Each call opens a new task, and a repeated name is an error. `config` and `inputs` are optional. A benchmark that wants two budgets declares two tasks.
- `@step()` and `@score()` bind to the most recently opened task. A task with no `@score()` is unscored. A module-level function called `score` is not picked up.
- `@step()` marks functions that run in declaration order. They are functions so that setup which is not a workflow invocation needs no schema escape hatch.
- A task swaps models by overriding the config tables. The harness has no model vocabulary of its own.

The helpers a tasks module reaches for live in the package as `paddock.tasks`. They drive stablemate across the process boundary, read the forensics a round left, and run the frozen-app, mutant, replay and greenfield rounds. Fixtures and rubrics those helpers read sit beside the benchmark's `tasks.py`. A private helper module may sit there too: the loader puts the benchmark folder on `sys.path` only while `tasks.py` is imported, so a top-level `import helper` works and nothing stays on the path afterwards. A benchmark calls `paddock.tasks.stablemate.install_agents(run)` as a step when its stage needs the agents layer rendered.

### The `run` handle

| | |
|---|---|
| `run.repo`, `run.stage` | the copy of the data repo the steps mutate. `run.repo` is the single-repo shorthand and refuses a folder of repos |
| `run.repos` | each staged repo by name, read-only: `{benchmark name: stage}` for a single repo, one entry per child of `data/` otherwise |
| `run.data` | the benchmark's own `data/` repo, which a step reads and never writes |
| `run.artifacts` | this step's artifact directory, kept in the workspace |
| `run.workdir(name)` | a fresh directory under `scratch/`, never copied into the result |
| `run.config` | the absolute path to the merged stablemate config |
| `run.cli(*argv, check=False, timeout=None)` | a subprocess, logged into `run.artifacts` |
| `run.project` | the tree the steps drive stablemate out of, pinned, see below |
| `run.inputs` | the task's declared inputs, read-only: str, number, bool or list of str |
| `run.benchmark` | the loaded benchmark: its root folder, name, base config, data path and tasks |
| `run.name` | the run's name: benchmark, task, data commit, stablemate sha, number |

Steps invoke workflows by subprocess of the real CLI. They never import workhorse in-process. The benchmark measures the surface an operator uses, and an in-process call would measure a different one. `run.cli` also aligns `PWD` to the working directory and drops `OLDPWD`. An agent CLI that resolves its project root from the environment would otherwise treat the harness's own repo as the project and commit its work there.

The stage is a clone of `data/` at HEAD with every remote removed. Uncommitted edits in `data/` are not in the copy, and the runner warns when it sees them. When `data/` is a folder of repos, each one is cloned under its own name in the stage, and the steps reach them as `run.repos["<name>"]`. A step that wants a tree to outlive the run copies it into `run.artifacts`.

### The project a round drives is pinned

A step runs stablemate's own CLIs out of a checkout (`uv run --project <checkout>
workhorse-coder …`). paddock does not hand it the operator's working tree: before the
first step it makes a **local clone with every remote removed**, checked out detached at
that checkout's HEAD, gives the steps *that* as `run.project`, and deletes it when the run ends. Three things fall out, and they are the whole reason:

- the round measures one commit of the code, even if the operator keeps editing theirs
  during a forty-minute trial;
- `ledger.json` records the pinned sha, so the ledger says which code produced its numbers,
  and whether the source was dirty (uncommitted edits are **excluded** by construction);
- a task's leak check — "did an agent write into the harness instead of its sandbox" —
  becomes exact, because nobody but the round has a reason to write in that tree.

A clone rather than a `git worktree`, because a worktree shares the live checkout's object
store *and* its `origin`. One round proved what that costs: an agent inside the pinned tree
read the toolchain's own AGENTS.md — "push it now, right after the commit" — obeyed it, and
its commits reached the public repo. Zero remotes is what makes that push fail loudly.

The pin is also **fenced**: its git directory is stashed beside the tree and `.git` becomes
a gitfile naming a path that does not exist, so the pinned tree is not a repository, git
stops walking up, and a commit cannot quietly land in a parent repo either.

None of that is a proof — an agent can `git init`, and the stash is one directory up from
the sandbox — so what the fence is paired with is a detector. When the steps end, `escaped()` asks the
stash what the round did to it and writes a `self-touched:` caveat into the ledger for each answer: the tree
was edited, the fence is gone, HEAD moved off the pinned sha, a ref appeared, objects exist
that the pinned sha does not reach (the patch-run-and-`reset --hard` shape), or the stash
itself is missing. A round whose numbers are not a measurement of the sha in its ledger
cannot be recorded without saying so.

`--no-pin-project` drives the checkout in place. A source git cannot clone — a directory
that is not a repository, or one with no commit yet — degrades to the same thing, with
`pinned: false` in the ledger rather than a failed round.

### A book run sees only its app

The pin keeps a round from writing into the toolchain. It does not keep an agent from
reading it. A book is written for an app that has no stablemate checkout beside it, so an
agent that learns the book's rules from stablemate's source writes a book no real
author could have written. One round's writer spent most of its turn reading ostler's
tests.

`paddock sandbox` runs a command in a container that has the tools and not the tree:

```bash
paddock sandbox build
paddock sandbox run --app WORKSPACE/stage --runs-dir DIR --config WORKSPACE/config.toml \
  -- workhorse-okf-book run --profile claude --runs-dir /runs --run-id ID --params '{...}'
```

`build` makes a wheel of every workspace member and installs those wheels in the image.
No source tree is copied in. It installs the Claude Code and opencode releases this
machine runs, unless `--claude-code-version` or `--opencode-version` names another.

`run` mounts these paths and nothing else:

- the app, at `/work/<its directory name>`, which is also the working directory;
- `--runs-dir`, at `/runs`, which should sit inside the run's workspace;
- `--config`, read-only, as the stablemate config;
- the login of each agent CLI the config runs, so the agents can call the model:
  `--credentials` for claude, `--opencode-auth` for opencode;
- your home skill folders, read-only, at the same place under the container's home:
  `~/.claude/skills` and `~/.agents/skills`, each only when it exists.

A run whose config names only opencode profiles gets only the opencode login.

The app's skills render from the published base library, which farrier fetches on first
use exactly as it would on a client's machine. `--base-library base-library` mounts this
checkout's library read-only instead, so a run can try skill edits that are not pushed yet.
Run `farrier --repo .` in the sandbox and commit the result before the book run, or the
app's pre-commit hook refuses every commit as drift.

The home skills let a run's prompts reference a skill you installed for yourself, as
they would on your machine. The run sees them but cannot change them.

It refuses a mount that would contain the checkout. The installed packages stay
readable inside the container, as they would be on any machine that installs them.

### Scoring is read-only

A `score(run)` function is called after the steps and must not touch what it measures: a
scored and an unscored run produce byte-identical results apart from `score.json`. This is
enforced — the staged tree is stat-manifested before and after, and a mutation fails the
run — because a score that edits the result makes the result a record of the scoring rather
than of the run, and every later comparison is then comparing the wrong thing. A score
function may write into its own `run.artifacts`, and may subprocess a judge CLI: a rubric
judged by a pinned model is still a way to be scored, it just lives in the task.

## The reaper

The stage is the reaper's warrant. When the steps end — finished, failed, or raised —
every process whose working directory is inside the stage is terminated, because the stage
is a directory only this round has and anything standing in it was put there by this
round. Agents leave servers running; a leftover one holds its port, and the *next* round on
the same task then finds its port answering with a valid `201` from a sibling — the one
intruder that looks exactly like success. Each survivor is logged at WARNING with its
command line rather than tidied away silently, because the leak is the agent's bug and the
reaper is only the net. A container is out of its reach: its working directory is inside
its own namespace, not the stage, so whatever brought the stack up still has to take it
down.

It fires from inside the round, which means a round **killed from outside** never fires it:
a `SIGTERM` to `paddock run` takes the runner down and leaves whatever it started standing
in the stage. Until there is a second invocation path, that case is manual — after killing
a round, list the survivors and finish the job:

```bash
for d in /proc/[0-9]*; do
  cwd=$(readlink "$d/cwd" 2>/dev/null) || continue
  case "$cwd" in */workspace/<benchmark>/<task>/*) echo "${d#/proc/} $cwd";; esac
done
```

Skipping it costs the *next* round on that task, not this one, which is why it is easy to
forget and expensive to have forgotten.

## Commands

```bash
paddock run <benchmark> <task>   # copy the data, run the steps, (score), write the result
paddock list                     # one line per task under gold/: benchmark, task, steps, scored or not
paddock sandbox build            # the image a book run is isolated in
paddock sandbox run ... -- CMD   # CMD in the app, with no stablemate checkout in sight
```

A run prints each step's outcome, the score and the result folder. It exits non-zero when a step failed.

## Tests

```bash
make -C paddock test
```

## Map

- `paddock/`: the package behind the `paddock` command.
