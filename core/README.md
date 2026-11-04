# stablemate-core

Shared plumbing for the [stablemate](https://github.com/GabrielCpp/stablemate) tools.

`workhorse`, `farrier` and `ostler` are independently installed tools. Workhorse is a
library used through workflow-owned commands; none of the three depends on another as
its public entry point. They share runtime state and must agree about it:

- **the home config** (`~/.config/stablemate/config.toml`) — `library_dir`,
  `stablemate_dir` and `base_dir` only mean anything if every tool reads the same value.
  One typed model declares every key. `farrier config reference` prints them.
- **the artifacts folder** — `artifacts_dir` is where per-user story artifacts (the specs
  tree) live, outside git and shared by every worktree. `$STABLEMATE_ARTIFACTS_DIR` wins,
  then `artifacts_dir`, then `<user data dir>/stablemate/artifacts`
  (`~/.local/share/stablemate/artifacts` on Linux);
- **the benchmark root** — `paddock_dir` holds paddock's `gold/`, `workspace/` and `results/`.
  It defaults to `<user data dir>/stablemate/paddock`;
- **base-library discovery** — one resolution order (`$STABLEMATE_BASE_DIR` → `base_dir`
  → a `stablemate_dir` checkout → the shared cache);
- **the base-library cache** (`~/.cache/stablemate`) — one directory, one layout, one
  fetch.
- **skill references** (`skill_refs.py`) — one rule for how a template names a skill.
  Farrier renders a link at install time and workhorse renders one at run time. Both
  must point at the same installed file. `scan_catalog` reads the skills a harness loads
  at run time: the folders from the cwd up to the repo root, the added dirs on Claude
  Code, then home.

This was duplicated code in both tools until the duplication caused a real bug: two
hand-rolled TOML writers, one of which stringified nested tables and silently destroyed
the other tool's `[power.*]` settings.

## Sharing code is not what makes the tools agree

Worth being precise, because it decides where the guards go: **one copy of this package
guarantees nothing.** The tools install separately and version independently, and the
config path comes from `platformdirs` — it is per *user*, not per venv. Two `pipx`
installs are two venvs, each resolving its own `stablemate-core`, both writing the one
file. Pip's resolver never sees across them.

So the invariant is enforced on the **file**, via `config_version` (see `config.py`): an
older build refuses to *write* a newer config, a newer build migrates an older one
forward, and a read of a newer file warns instead of failing, so a week-long run
cannot be killed by another tool's upgrade. That guard holds however the tools got installed: separate venvs, one shared
venv, even vendored copies.

What this package buys is therefore ordinary: one implementation to fix bugs in, one
resolution order to reason about. Useful, but not the thing standing between you and a
corrupted config.

It depends on nothing else in the workspace and must not: `workhorse → core`,
`farrier → core` and `ostler → core`, never back. It knows no workflow's vocabulary, no
node types, and nothing about library content — only where files live and how they are
read.

## It is vendored, not published

Because the guard above holds however the tools got installed, this package is not a
distribution. Five tools carry it: farrier, workhorse, ostler, paddock and saddlebag.
In a checkout each one holds a symlink to this directory:

```
farrier/farrier/_vendor/stablemate_core       ->  ../../../core/stablemate_core
workhorse/workhorse/_vendor/stablemate_core   ->  ../../../core/stablemate_core
ostler/ostler/_vendor/stablemate_core         ->  ../../../core/stablemate_core
paddock/paddock/_vendor/stablemate_core       ->  ../../../core/stablemate_core
saddlebag/saddlebag/_vendor/stablemate_core   ->  ../../../core/stablemate_core
```

A built wheel or sdist holds real files at that path, because the build follows the link.
Imports read `farrier._vendor.stablemate_core` in both places, and an installed tool needs
no core checkout.

Next to each link sits `stablemate_core.sha256`, a digest of every file in this package.
It exists for a release reason. Release-please decides which package to bump from the
paths a commit touched, and it has no option to watch another path. A fix committed only
under `core/` touches no released package and would ship to nobody. Running `make vendor`
in the same commit rewrites each digest, which touches every tool and releases it. The
digest covers only this package, so a change to core tests alone rewrites nothing.
`make check-vendor` fails, naming the tool, when a link is missing or points elsewhere or
a digest is stale.

Two consequences to keep in mind when changing anything here:

- **Every import inside this package must be relative.** The same file is imported under
  several names, and an absolute `from stablemate_core.x import y` resolves to whichever
  one is on `sys.path`. A vendored module would reach back out of the wheel that contains
  it. The repo-wide ban on relative imports is lifted for exactly this package, in the
  root `pyproject.toml`.
- **A new dependency has to be added to every tool that vendors this.** `check-vendor`
  checks links and digests. It cannot notice a requirement that only `core/pyproject.toml`
  declares.

You do not install this directly, and you cannot: the `Private :: Do Not Upload`
classifier makes PyPI reject it.
