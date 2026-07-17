# stablemate-core

Shared plumbing for the [stablemate](https://github.com/GabrielCpp/stablemate) tools.

`workhorse` and `farrier` are independent CLIs — neither imports the other — but they
share runtime state, and they must agree about it:

- **the home config** (`~/.config/stablemate/config.toml`) — `library_dir`,
  `stablemate_dir` and `base_dir` only mean anything if every tool reads the same value;
- **base-library discovery** — one resolution order (`$STABLEMATE_BASE_DIR` → `base_dir`
  → a `stablemate_dir` checkout → the shared cache);
- **the base-library cache** (`~/.cache/stablemate`) — one directory, one layout, one
  fetch.

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
forward, and reads stay fail-soft so a week-long run cannot be killed by another tool's
upgrade. That guard holds however the tools got installed — separate venvs, one shared
venv, even vendored copies.

What this package buys is therefore ordinary: one implementation to fix bugs in, one
resolution order to reason about. Useful, but not the thing standing between you and a
corrupted config.

It depends on nothing else in the workspace and must not: `workhorse → core` and
`farrier → core`, never back. It knows no workflow's vocabulary, no node types, and
nothing about library content — only where files live and how they are read.

You do not install this directly; the tools depend on it.
