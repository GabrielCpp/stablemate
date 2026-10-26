# After a run

## The result

```
results/<benchmark>/<task>/<data commit>-<code commit>/<n>/
  ledger.json   steps, durations, commands, exit codes, pinned sha, dirty flag, the HEAD of each staged repo under `repos`, caveats
  score.json    the Score the task returned, or null
  config.toml   the merged config the run used
  stage/        the after-state of the copy
```

The step logs stay in `workspace/…/artifacts/<step>/`. Read them there when a step
failed. A scored and an unscored run of the same round differ only by `score.json`.

The ledger's caveats come from the pin's detector. Each `self-touched:` line names one
way the round wrote into the pinned code: the tree was edited, the fence is gone, HEAD
moved off the pinned sha, a ref appeared, unreachable objects exist, or the stash is
missing. `pinned: false` means the run drove the checkout in place, either because of
`--no-pin-project` or because the source could not be cloned. Neither ledger supports a
claim about one commit of the code.

## Isolating a book run

The pin stops a round from writing into the toolchain. It does not stop an agent from
reading it, and a book written from the toolchain's source is a book no real author of
your app could write. `paddock sandbox` runs the command in a container that holds the
installed tools and no source tree. `build` turns the checkout paddock runs from into
wheels and installs those.

```bash
paddock sandbox build
paddock sandbox run --app WORKSPACE/stage --runs-dir DIR --config WORKSPACE/config.toml \
  -- workhorse-okf-book run --profile claude --runs-dir /runs --run-id ID --params '{...}'
```

- Repeat `--app` for each repo of a workspace and name the one the command starts in with
  `--workdir`. The flag is needed with several `--app` and optional with one.
- The container mounts each app at `/work/<its directory name>`, the `--workdir` one as its working directory, `--runs-dir` at `/runs`, the
  config read-only, the login of each agent CLI the config names, and the home skill
  folders read-only. Nothing else.
- Put `--runs-dir` inside the run's workspace so the result keeps it.
- Skills render from the published base library. `--base-library PATH` mounts a
  local library folder instead, to try skill edits that are not pushed.
- Run `farrier --repo .` in the sandbox and commit its output before the book run.
  Without that the app's pre-commit hook refuses every commit as drift.
- `paddock sandbox run --help` lists the remaining flags.

## A run killed from outside

The **reaper** fires when the steps end. It terminates every process whose working
directory is inside the stage and logs each one at WARNING. A `SIGTERM` to `paddock run`
takes the runner down before the reaper fires, so every server the round started keeps
running, holds its port, and answers the next round on that task with a sibling's valid
response. That next round then scores a leftover as success.

After killing a round, list the survivors and terminate them:

```bash
for d in /proc/[0-9]*; do
  cwd=$(readlink "$d/cwd" 2>/dev/null) || continue
  case "$cwd" in */workspace/<benchmark>/<task>/*) echo "${d#/proc/} $cwd";; esac
done
```

Containers are out of the reaper's reach in every case. Whatever brought a compose stack
up takes it down.

Then `paddock resume <benchmark> <task>` continues the killed round on its pinned sha.
Its ledger shows the killed segment with no end, and that segment's self-touched check is
lost with its pin.
