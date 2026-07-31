---
type: concept
slug: library-directory
title: Library directory
---
# Library directory

A prompt-library root farrier renders from — a tree holding `library/` (skills, prompts, roots),
and optionally `packs/`, `scaffolds/` and `workflows/`. farrier ships no library content of its
own; every install run resolves the *overlay* library first via `resolve_library_dir`, then stacks
it above the *base* library via `set_layers`, and every content lookup afterwards goes through that
stack. It is touched at the top of [`install`](../farrier.md#install)'s `does:` and also
independently by [`source`](../farrier.md#source), which resolves it to look up a generated file's
editable origin.

- code: `farrier/farrier/layers.py::resolve_library_dir`
- verify: `farrier/tests/test_config_resolution.py::test_precedence_flag_over_env_over_config`

### Resolution precedence

`resolve_library_dir(cli_library)` picks the first overlay candidate present, in order:

1. `cli_library` — the `--library DIR` flag (`install`'s or `source`'s), if passed.
2. `$FARRIER_LIBRARY_DIR` — the environment variable, if set to a non-empty value.
3. `library_dir` — the `library_dir` key in the [shared home config file](../home-config.md), if
   present (read by `read_config`).

**None of the three yielding a candidate is not automatically an error.** If a base library is
installed, `resolve_library_dir` returns `None` and farrier runs base-only — a supported setup, and
the one a public reader gets with no configuration at all. `SystemExit` with a
`farrier config set-library` setup hint is raised only when there is *neither* an overlay *nor* a
base.

Otherwise the candidate is expanded (`~`) and resolved to an absolute path, then validated by
`is_library_dir` — a directory is usable when it contains a `library/` subdirectory. `packs/` is
deliberately **not** required: the base library ships scaffolds and the stablemate skills with no
packs at all, and a repo selects from it directly in `agents.yml` (`skills: [stablemate/*]`). An
unusable resolved path raises `SystemExit`, naming which source (`--library` /
`$FARRIER_LIBRARY_DIR` / the config file path) produced it.

`is_library_dir` lives in `stablemate_core` rather than in farrier because workhorse must agree
with farrier about what a library is: a base one tool can see and the other cannot is
indistinguishable, from the outside, from the library being broken.

- code: `core/stablemate_core/layout.py::is_library_dir`
- verify: `farrier/tests/test_config_resolution.py::test_unresolved_errors_with_hint`
- verify: `farrier/tests/test_config_resolution.py::test_bad_library_path_errors`
- verify: `farrier/tests/test_config_resolution.py::test_no_overlay_is_fine_when_base_is_installed`

### The layer stack

There is no longer a set of module-global path constants pointing at one library root. `main` calls
`set_layers(overlay)`, which builds an ordered `LAYERS` list — the resolved overlay first (if any),
then the base library returned by `stablemate_core.discovery.base_library_dir()` (if installed) —
and content is looked up across that stack, highest precedence first. A higher layer shadows a
lower one **name-for-name**, which is how an overlay overrides a base skill, pack or workflow
without forking it.

`LAYERS` is mutated in place rather than rebound, so a `from farrier.layers import LAYERS` binding
elsewhere tracks the current stack instead of a stale snapshot. Each `Layer` carries a `name`
alongside its `root` (the overlay's path, or `"base-library (base)"`) — without it, an overlay
silently shadowing a base skill is invisible, and you would edit the base copy and watch the
overlay's get rendered instead.

| helper | answers |
|---|---|
| `layer_dirs(*parts)` | every `(layer, dir)` holding `<root>/<parts>`, in precedence order |
| `find_in_layers(*parts)` | the highest-precedence layer holding `<root>/<parts>`, or `None` |
| `available_names(*parts, suffix=, dirs=)` | every name any layer provides there, deduplicated — the "here is what does exist" half of a selection error |
| `searched_layers()` | the stack as text — the "here is where I looked" half |

So the paths the old globals named are now `parts` tuples passed to these helpers:
`("library", "skills")` and `("library", "prompts")` for the selected sources,
`("library", "roots", f"{root}.md")` for a Copilot root instruction, and `("workflows", name)` for
a workflow the launcher will point at.

- code: `farrier/farrier/layers.py::set_layers`
- verify: `farrier/tests/test_config_resolution.py::test_overlay_shadows_base`
- verify: `farrier/tests/test_config_resolution.py::test_unknown_pack_names_the_layers`

### Persisting the config-file candidate

`farrier config set-library <path>` (see [`config`](../farrier.md#config)) is how the home-config
candidate (precedence 3) gets written: it validates the path with the same `is_library_dir` check,
then calls `write_library_dir`, which persists the `library_dir` field of the
[home config file](../home-config.md) alongside any other keys already there (e.g.
`stablemate_dir`, `base_dir`).

- code: `core/stablemate_core/config.py::write_library_dir`
