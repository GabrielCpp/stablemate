# paddock

The enclosure where horses are worked and evaluated. **One benchmark harness**: seeds,
tasks, results.

```
unpack a seed  ->  run the steps  ->  stage the result  ->  (score it)
```

[`data/`](data/README.md) is this tool's data — task modules and their tests, pointer
files, config TOMLs and the frozen application material tasks reference. `paddock/` beside
it is the code that runs them.

`data/` is not "the part with no code in it": the task modules under `data/tasks/` are
Python, and so are the tests under `data/tests/` that hold them honest. The split is by
*subject*, not by language — what a round measures lives in `data/`, and the machinery
that unpacks, drives, stages and seals a round lives in the package. It is a sibling of
the package rather than a subdirectory because `[tool.hatch.build]` names the inner
`paddock` directory: a sibling `data/` ships in no wheel and no sdist, which is what keeps
a hundred-odd fixture files out of every install of the tool.

## The four nouns

**Seed** — a zip of a whole repository, `.git` included: the committed history as of
capture, the working tree exactly as it was (uncommitted edits and all), and the
farrier-installed layer already in place. "The repo can be in different states" is not a
schema; it is *when you captured the zip*.

**Task** — a Python module under `data/tasks/<name>.py` naming a seed, a stablemate
config, an ordered list of steps and (optionally) a score function.

**Result** — the staged after-state: the mutated repo, each step's artifacts, and a
ledger. Zipped and pointed at exactly like a seed — a result is a seed pointed the other
way.

**Score** — a ruler the *task* brought. There is no harness-side judging; a task either
measures itself or leaves its output for whoever is driving the session to read.

## Zips are never tracked

`scripts/check_public.py` scans a binary file **by path only** — a NUL byte in the first
8 kB stops the content scan — so a tracked zip would ship its contents straight past the
guard that exists to catch exactly that. What git carries is a small TOML pointer:

```toml
name = "policy-desk"
repo_dir = "policy-desk"     # the directory name the zip unpacks back into
sha256 = "…"
bytes = 214_000_000
head = "9e3536d…"
dirty = false
url = "https://…"            # optional; the first fetch backend is a plain HTTPS GET
source = "apps/policy-desk"  # where the captured tree lives, when it lives in this repo
tree_sha256 = "…"            # that directory's content hash at capture time
```

The sha256 makes the fixture reproducible and its integrity independent of transport, and
it is verified on every unpack — not only after a download. A seed in the local store was
put there by some earlier command, and a fixture that has quietly drifted is a benchmark
number nobody can attribute.

`source` and `tree_sha256` answer the other question, and it is the one a fixture author
trips over. A round materializes from the unpacked zip, while the answer key is read from
the tracked tree — so an edit to `data/apps/<app>/` that never reached a re-capture leaves
every trial facing the previous content with the new key held against it, and nothing about
the run looks wrong. `data/tests/test_seed_freshness.py` recomputes the hash and fails with
the re-capture command in the message. A seed captured from outside the data directory
records no `source` and is exempt by construction: there is no in-tree tree it could have
drifted from.

`repo_dir` looks cosmetic and is not: farrier derives the names of the files it generates
from the repo directory's basename, so a tree unpacked under a different name gets a fresh
set of generated skills while the ones the seed carries dangle.

## Writing a task

```python
"""What this task measures, in one paragraph."""
from paddock import Score, step, task

task(
    name="policy-desk-qa",
    seed="policy-desk",                # data/seeds/policy-desk.toml
    config="configs/opencode.toml",    # a full stablemate config, tracked, under data/
)

@step()
def seed_defect(run):
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

def score(run) -> Score:            # optional
    return Score(headline="caught 7/9  missed 2", data={...})
```

- `task()` — exactly once per module, before the steps.
- `@step()` — functions, run in declaration order. They are functions precisely so setup
  that is *not* a workflow invocation needs no schema escape hatch.
- A task swaps models by swapping its config file; the config carries the `[power.*]` /
  `[profiles.*]` tables, which is why the harness has no model vocabulary of its own.

### The `run` handle

| | |
|---|---|
| `run.repo` | the unpacked seed, inside the staging area — the tree the steps mutate |
| `run.artifacts` | this step's artifact directory, sealed into the result |
| `run.workdir(name)` | a fresh directory under `scratch/`, **not** sealed into the result |
| `run.config` | the absolute path to the task's stablemate config |
| `run.cli(*argv, check=False, timeout=None)` | a subprocess, logged into `run.artifacts` |
| `run.project` | the tree the steps drive stablemate out of — pinned, see below |
| `run.seed`, `run.data_dir`, `run.store`, `run.label` | where everything came from |

Steps invoke workflows by **subprocess of the real CLI**, never by importing workhorse
in-process. That is not purity: the benchmark measures the surface an operator uses, and
an in-process call would measure a different one. `run.cli` also aligns `PWD` to the
working directory and drops `OLDPWD`, because an agent CLI that resolves its project root
from the environment will otherwise treat the harness's own repo as the project and commit
its work there.

### The project a round drives is pinned

A step runs stablemate's own CLIs out of a checkout (`uv run --project <checkout>
workhorse-coder …`). paddock does not hand it the operator's working tree: before the
first step it makes a **local clone with every remote removed**, checked out detached at
that checkout's HEAD, gives the steps *that* as `run.project`, and deletes it after
sealing. Three things fall out, and they are the whole reason:

- the round measures one commit of the code, even if the operator keeps editing theirs
  during a forty-minute trial;
- `steps.json` records the pinned sha, so the ledger says which code produced its numbers,
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
the sandbox — so what the fence is paired with is a detector. At seal, `escaped()` asks the
stash what the round did to it and seals a `self-touched:` caveat for each answer: the tree
was edited, the fence is gone, HEAD moved off the pinned sha, a ref appeared, objects exist
that the pinned sha does not reach (the patch-run-and-`reset --hard` shape), or the stash
itself is missing. A round whose numbers are not a measurement of the sha in its ledger
cannot be recorded without saying so.

`--no-pin-project` drives the checkout in place. A source git cannot clone — a directory
that is not a repository, or one with no commit yet — degrades to the same thing, with
`pinned: false` in the ledger rather than a failed round.

`workdir()` exists for tasks that fan out — one fresh tree per trial. A result zip
carrying nine copies of a repo is a result nobody keeps, so what a step wants preserved it
copies into `run.artifacts`, which makes that an explicit decision.

### Scoring is read-only

A `score(run)` function is called after the steps and must not touch what it measures: a
scored and an unscored run produce byte-identical results apart from `score.json`. This is
enforced — the staged tree is stat-manifested before and after, and a mutation fails the
run — because a score that edits the result makes the zip a record of the scoring rather
than of the run, and every later comparison is then comparing the wrong thing. A score
function may write into its own `run.artifacts`, and may subprocess a judge CLI: a rubric
judged by a pinned model is still a way to be scored, it just lives in the task.

## The staging layout

```
<store>/work/<task>/<label>/
  stage/                     <- everything here, and only this, becomes the result zip
    <repo_dir>/              <- the unpacked seed, mutated by the steps
    artifacts/<step>/        <- run dirs, logs, exit codes
    steps.json               <- order, outcome, duration, every command run
    score.json               <- only when the task brought a score function
  scratch/                   <- the steps' own working space, never sealed
```

The store defaults to `~/.local/share/stablemate/paddock` — off `/tmp`, which does not
survive a reboot. A fixture that evaporates is not a fixture.

`stage/` is also the reaper's warrant. When the steps end — finished, failed, or raised —
every process whose working directory is inside `stage/` is terminated, because the stage
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
  case "$cwd" in */paddock/work/<task>/<label>/*) echo "${d#/proc/} $cwd";; esac
done
```

Skipping it costs the *next* round on that task, not this one, which is why it is easy to
forget and expensive to have forgotten.

## Commands

```bash
paddock seed capture <repo> --name X   # repo state -> zip + tracked pointer
paddock seed unpack <name> --to DIR    # pointer -> verified local tree
paddock fetch <name>                   # url -> local store, sha256-verified
paddock run <task> [--label L] [--param K=V]   # unpack, steps, stage, (score), seal
paddock list                           # tasks and their seeds
```

`--param KEY=VALUE` (repeatable) is how a task is run *smaller* than its full self — one
defect instead of eleven, a shorter budget — without editing the module or growing a
second task. A step reads it with `run.param("name")` (plus `param_list` / `param_float` /
`param_bool`), and the value is recorded in `steps.json` and in the result pointer's note,
because a narrowed run is a different measurement and one that does not say so invites a
comparison against a full run nobody would have made on purpose.

Seeds are born by `capture`, not by hand: hand-zipping is what lets a `.venv` into a
fixture, and the command is the contract's enforcement point — it refuses build output and
local environments anywhere in the tree (`--exclude GLOB` permits one deliberately), warns
when farrier was never run, and records HEAD.

`unpack` re-runs `farrier install` against the extracted tree, because the machine-local
layer a zip reproduces faithfully is a layer pointing at the capture machine's paths. Pass
`--no-install` to skip it; when farrier is absent or fails, the unpack still succeeds and
says so rather than leaving a silently stale tree.

## Tests

```bash
make -C paddock test
```
