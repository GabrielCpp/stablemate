---
type: concept
slug: library-directory
title: Library directory
---
# Library directory

The prompt-library root farrier renders from — the `agents/` tree holding `library/` (skills,
prompts, roots), `packs/` (pack definitions), `scaffolds/`, and `workflows/`. farrier ships no
library content of its own; every install run resolves this directory first via
`resolve_library_dir`, then points a set of module-global path constants at it via
`set_library_globals`. It is touched at the top of [`install`](../farrier.md#install)'s `does:`
and also independently by [`source`](../farrier.md#source), which resolves it to look up a
generated file's editable origin.

- code: `farrier/farrier/install.py::resolve_library_dir`
- verify: `farrier/tests/test_config_resolution.py::test_precedence_flag_over_env_over_config`

### Resolution precedence

`resolve_library_dir(cli_library)` picks the first candidate present, in order:

1. `cli_library` — the `--library DIR` flag (`install`'s or `source`'s), if passed.
2. `$FARRIER_LIBRARY_DIR` — the environment variable, if set to a non-empty value.
3. `library_dir` — the `library_dir` key in the shared home config file (`config.toml` at an
   OS-appropriate path via `platformdirs.user_config_dir("farrier")`, e.g.
   `~/.config/farrier/config.toml` on Linux; read by `read_config`), if present.

If none of the three yield a candidate, it raises `SystemExit` with a setup hint pointing at
`farrier config set-library`. Otherwise the candidate is expanded (`~`) and resolved to an absolute
path, then validated by `is_library_dir` — a directory is usable only when it contains both a
`library/` and a `packs/` subdirectory. An unusable resolved path also raises `SystemExit`, naming
which source (`--library` / `$FARRIER_LIBRARY_DIR` / the config file path) produced it.

- code: `farrier/farrier/install.py::is_library_dir`
- verify: `farrier/tests/test_config_resolution.py::test_unresolved_errors_with_hint`
- verify: `farrier/tests/test_config_resolution.py::test_bad_library_path_errors`

### Module globals populated

Once resolved, `set_library_globals(root)` points these `farrier.install` module globals at the
root — the rendering helpers throughout the module read them directly rather than threading the
root as a parameter:

| global | path |
|---|---|
| `AGENTS` | `root` |
| `LIBRARY` | `root/library` |
| `PACKS` | `root/packs` |
| `SKILLS` | `root/library/skills` |
| `PROMPTS` | `root/library/prompts` |
| `ROOTS` | `root/library/roots` |
| `SCAFFOLDS` | `root/scaffolds` |
| `WORKFLOWS` | `root/workflows` |

`set_library_globals` only assigns these eight globals from `root` — it calls nothing else and
reads no filesystem state itself (resolution and validation happen earlier, in
`resolve_library_dir`/`is_library_dir`).

- code: `farrier/farrier/install.py::set_library_globals`
- verify: `farrier/tests/test_config_resolution.py::test_set_library_globals`

### Persisting the config-file candidate

`farrier config set-library <path>` (see [`config`](../farrier.md#config)) is how the home-config
candidate (precedence 3) gets written: it validates the path with the same `is_library_dir` check,
then calls `write_library_dir`, which persists the `library_dir` field of the
[home config file](../home-config.md) alongside any other keys already there (e.g.
`stablemate_dir`).

- code: `farrier/farrier/install.py::write_library_dir`

