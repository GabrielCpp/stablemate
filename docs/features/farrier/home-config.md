---
type: format
slug: home-config
title: Home config file (config.toml)
---
# Home config file (config.toml)

The shared, machine-local settings file every stablemate tool reads and writes — holding the
overlay [library directory](concepts/library-directory.md) candidate, the base-library path, the
local `stablemate` checkout path, and the per-backend `power`/`harness` tables workhorse resolves
against. It lives in `stablemate_core`, not in farrier: the keys are shared, so workhorse
inheriting a farrier-set `library_dir` is the point rather than a leak. Read by `load_config`
(farrier spells the same function `read_config`; it is an alias, not a second implementation),
written key-by-key by `write_config_key`, and surfaced to the user by
[`farrier config show`](farrier.md#config).

- file: `config.toml` under `platformdirs.user_config_dir("stablemate")` — e.g.
  `~/.config/stablemate/config.toml` on Linux, `~/Library/Application Support/stablemate/config.toml`
  on macOS, `%APPDATA%\stablemate\config.toml` on Windows. `$STABLEMATE_CONFIG` (or the
  pre-unification `$WORKHORSE_CONFIG`) overrides the path outright.
- code: `core/stablemate_core/config.py::load_config`

## Fields

A TOML table. `write_config_key` merges into whatever keys already exist rather than replacing the
file, so any key is legal — these are the ones the tools actually read back. (`power.*` and
`harness.*` are nested tables owned by workhorse; see workhorse's own docs for their shape.)

### library_dir
- type: `string` — required: no — default: unset

The [library directory](concepts/library-directory.md) resolution's third-precedence *overlay*
candidate (after `--library` and `$FARRIER_LIBRARY_DIR`). Written by
[`farrier config set-library <path>`](farrier.md#config) via `write_library_dir`, after the path is
validated with `is_library_dir` (must contain `library/`).

### base_dir
- type: `string` — required: no — default: unset

An explicit on-disk path to the *base* library content — the persisted form of
`$STABLEMATE_BASE_DIR`. Written by `write_base_dir`. Consulted by `base_library_dir()` second,
after the env var and before a `stablemate_dir`-derived checkout path; a configured-but-invalid
value is skipped rather than raised on, because the base is additive and failing soft keeps an
overlay-only setup working.

### stablemate_dir
- type: `string` — required: no — default: unset

The local `stablemate` checkout path (holds the workhorse runtime and the farrier installer source)
used for `SRC=1` local-source runs of the generated agent launcher, and as the third route to a base
library (`<checkout>/base-library`). Written by
[`farrier config set-stablemate <path>`](farrier.md#config) via `write_stablemate_dir` — unlike
`library_dir`, the path is persisted as-is with no directory-shape validation. Read back by
`resolve_stablemate_dir`, which returns `None` when the key is unset.

- code: `core/stablemate_core/config.py::write_stablemate_dir`

### worktree_dir
- type: `string` — required: no — default: unset

The parent directory new git worktrees are cut into — `git worktree add "$worktree_dir/<repo>-<slug>"`.
Machine-local disk layout rather than a repo property: one machine keeps worktrees on a data
volume, another under `~`, and no repo can commit an answer that is right on both. Written by
[`farrier config set-worktree <path>`](farrier.md#config) via `write_worktree_dir`, persisted as-is
with **no existence check** — the path names where worktrees *will* be created, so requiring it to
exist would make the machine unconfigurable before the first worktree. Read back by
`resolve_worktree_dir`, which returns `None` when unset; no tool defaults it, because inventing a
location would scatter worktrees across a machine that has a configured home for them. The reader
is an agent: the base library's `implement-plan` command resolves it with
`farrier config show worktree_dir` before branching.

- code: `core/stablemate_core/config.py::write_worktree_dir`

### user_library
- type: `table of tables` — required: no — default: absent (nothing is installed at user scope)

The personal library: which skills and prompts
[`farrier install --user`](farrier.md#install---user) renders into the harness home directories,
for every project rather than per repo. One table per harness — `[user_library.claude]`,
`[user_library.codex]`, `[user_library.copilot]` — each holding the same
`skills` / `prompts` / `exclude` keys [`agents.yml`](agents-yml-config.md) uses, plus one shared
`[user_library.template]` table supplying `{{ template.* }}` values. A harness with no table gets
nothing; an unknown table name is an error rather than a silent no-op, because a typo'd harness
is indistinguishable from one that was never configured.

```toml
[user_library.claude]
skills = ["stablemate/*"]
prompts = ["stablemate/grill"]

[user_library.codex]
skills = ["stablemate/ostler"]

[user_library.template]
backend_layer_name = "Go API"
```

It lives here rather than in a repo because that is the whole point: a skill that needs nothing
from the checkout it is invoked in was being installed into every checkout and drifting in each
one. `prompts` is Claude-only — the other harnesses have no personal command directory — and
naming it elsewhere is a hard error. There is **no setter subcommand**: these are nested tables,
and `write_config_key`'s flat assignment cannot express one.

- code: `farrier/farrier/user_library.py::user_library_tables`

### config_version
- type: `integer` — required: no — default: absent (treated as version 0)

The schema version this file was last written under, stamped on **every** write. It is not the
`stablemate-core` package version: coupling the two would bump the schema on every patch release and
lock out every tool that had not upgraded yet. A file newer than the running build's
`CONFIG_VERSION` makes `write_config_key` refuse with `ConfigVersionError` rather than clobber it —
the one guard that holds however the tools were installed, because it defends the file rather than
trusting the code that reaches it. An older file is carried forward by `_migrate_forward` before the
write lands, so a write never mixes schemas.

## Reading and writing

- `load_config()` — returns the parsed unified file if it exists. If it does not, and the path was
  **not** named explicitly, the pre-unification per-tool files (`user_config_dir("workhorse")` then
  `user_config_dir("farrier")`, merged in that order) are read as a fallback; an explicitly named
  `$STABLEMATE_CONFIG` that happens not to exist means "this file", not "and also whatever is in
  `~/.config/workhorse`". A corrupt or unreadable file parses to `{}` rather than raising — an
  unattended run must not die on a bad config, and every caller already handles "nothing
  configured".
- `write_config_key(key, value)` — creates the config directory if needed, reads the existing config
  via `load_config`, applies the version guard/migration above, sets `key = value`, stamps
  `config_version`, and rewrites the whole file with a real TOML writer (`tomli_w`). When only
  legacy files exist, this is what merges them into the unified path. Using a TOML writer is
  load-bearing: the hand-rolled `f'{k} = "{v}"'` it replaced stringified nested tables, so a single
  `config set-base` turned `[power.*]` into a Python-repr string and every node silently fell back
  to the default model with no error anywhere.

- code: `core/stablemate_core/config.py::write_config_key`
