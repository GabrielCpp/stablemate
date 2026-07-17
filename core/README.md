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

It depends on nothing else in the workspace and must not: `workhorse → core` and
`farrier → core`, never back. It knows no workflow's vocabulary, no node types, and
nothing about library content — only where files live and how they are read.

You do not install this directly; the tools depend on it.
