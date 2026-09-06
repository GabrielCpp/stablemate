---
type: concept
slug: library-directory
title: Library directory
---
# Library directory

A prompt-library root farrier renders from — a tree holding `library/` (skills, prompts, roots),
and optionally `packs/` and `scaffolds/`. farrier ships no library content of its
own; every install run resolves the *overlay* library first via `resolve_library_dir`, then stacks
it above the *base* library via `set_layers`, and every content lookup afterwards goes through that
stack. It is touched at the top of [`install`](../farrier.md#install)'s `does:` and also
independently by [`source`](../farrier.md#source), which resolves it to look up a generated file's
editable origin.

- code: `farrier/farrier/layers.py::resolve_library_dir`
- tests: `farrier/tests/test_config_resolution.py::test_precedence_flag_over_env_over_config`
- detail: [library layer](library-layer.md)

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

- code: `farrier/farrier/_vendor/stablemate_core/layout.py::is_library_dir`
- code: `farrier/farrier/_vendor/stablemate_core/layout.py`
- tests: `farrier/tests/test_config_resolution.py::test_unresolved_errors_with_hint`
- tests: `farrier/tests/test_config_resolution.py::test_bad_library_path_errors`
- tests: `farrier/tests/test_config_resolution.py::test_no_overlay_is_fine_when_base_is_installed`

### Fetching and updating the base

The base library resolves through `stablemate_core.discovery` in four steps —
`$STABLEMATE_BASE_DIR` → the `base_dir` config key → a `stablemate_dir` checkout
(`<checkout>/base-library`) → the shared cache at `~/.cache/stablemate`. Only the last of those
can be produced on demand, and [`install`](../farrier.md#install) is the one command that produces
it: it calls `ensure_base_library_dir(refresh=not --check)` before resolving anything, which
fetches the cache when absent and updates it to the head of `main` when present.

Two functions, deliberately: `base_library_dir()` is a pure lookup and `ensure_base_library_dir()`
is the explicit form allowed to reach the network. A resolution that downloads as a side effect is
a trap — `farrier config show` would trigger it, and so would any test that resolves a path.

**Routes 1–3 are never fetched over, and not even probed.** They each name a base a human chose, so
`ensure_base_library_dir` returns immediately when one answers. That is what makes the ordering
guarantee hold under the command that downloads: a checkout you are editing cannot have a copy
appear underneath it.

**Everything except install reads the cache frozen.** No lookup, no workhorse resume and no timer
refreshes it — a cache tracking `main` live could resume a week-long run into a different library
than it started with. Install is exempt because it is an operator asking for a re-render at a
moment they chose, which is the same authority `rm -rf ~/.cache/stablemate` always carried.

Updating asks the remote for the head of `main` (`git ls-remote`, a few hundred bytes) before
cloning anything, so an already-current cache costs one round-trip instead of a re-clone. Every
failure — unreachable remote, `STABLEMATE_FETCH_BASE=0`, a clone that dies, a fetched tree that
holds no `library/` — leaves the existing cache untouched and returns it. That asymmetry is the
point: a *fetch* that fails has nothing to hand back, but a *refresh* that fails still has a good
library, and turning that into "no library" would make an offline machine worse off for asking.

- code: `farrier/farrier/_vendor/stablemate_core/discovery.py::ensure_base_library_dir`
- code: `farrier/farrier/_vendor/stablemate_core/base_cache.py::refresh_cached_base`
- code: `farrier/farrier/_vendor/stablemate_core/discovery.py`
- code: `farrier/farrier/_vendor/stablemate_core/base_cache.py`
- tests: `core/tests/test_discovery.py::test_ensure_never_fetches_over_a_chosen_base`
- tests: `core/tests/test_base_cache.py::test_refresh_does_not_clone_when_already_current`
- tests: `core/tests/test_base_cache.py::test_refresh_keeps_the_cache_when_the_remote_is_unreachable`

### The layer stack

There is no longer a set of module-global path constants pointing at one library root. `main` calls
`set_layers(overlay)`, which builds an ordered `LAYERS` list — the resolved overlay first (if any),
then the base library returned by `stablemate_core.discovery.base_library_dir()` (if installed) —
and content is looked up across that stack, highest precedence first. A higher layer shadows a
lower one **name-for-name**, which is how an overlay overrides a base skill, pack or scaffold
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
| `available_names(*parts, suffix=)` | every name any layer provides there, deduplicated — the "here is what does exist" half of a selection error |
| `searched_layers()` | the stack as text — the "here is where I looked" half |

So the paths the old globals named are now `parts` tuples passed to these helpers:
`("library", "skills")` and `("library", "prompts")` for the selected sources,
`("library", "roots", f"{root}.md")` for a Copilot root instruction, and
`("packs", f"{pack_id}.yml")` for a pack.

- code: `farrier/farrier/layers.py::set_layers`
- tests: `farrier/tests/test_config_resolution.py::test_overlay_shadows_base`
- tests: `farrier/tests/test_config_resolution.py::test_unknown_pack_names_the_layers`

## Fields

### field: LAYERS
- type: `list[Layer]`
- default: `[]`
- verify: count(subject="LAYERS", equals=0)
- required: true
- verify: count(subject="initial LAYERS", equals=0)
- semantics: process-local ordered stack of configured library layers, highest precedence first
- code: `farrier/farrier/layers.py::LAYERS`

### field: BASE_LAYER_NAME
- type: `str`
- default: `base-library (base)`
- verify: json_path(path="return value", equals="base-library (base)")
- required: true
- verify: json_path(path="return value", equals="base-library (base)")
- semantics: provenance label assigned to the installed base layer
- verify: json_path(path="Layer.name", equals="base-library (base)")
- code: `farrier/farrier/layers.py::BASE_LAYER_NAME`

## Methods

### method: set_layers
- sig: `set_layers(overlay: Path | None) -> None`
- does: places the supplied overlay first when it is present
- does: appends the installed base layer after the overlay when a base exists
- does: updates the existing `LAYERS` list in place
- returns: `None`
- verify: count(subject="configured library layers", equals=2)
- code: `farrier/farrier/layers.py::set_layers`
- tests: `farrier/tests/test_config_resolution.py::test_overlay_shadows_base`

### method: layer_dirs
- sig: `layer_dirs(*parts: str) -> list[tuple[Layer, Path]]`
- does: returns one entry for each layer containing the requested directory
- returns: entries in layer precedence order
- verify: count(subject="matching layer directories", equals=1)
- code: `farrier/farrier/layers.py::layer_dirs`

### method: find_in_layers
- sig: `find_in_layers(*parts: str) -> tuple[Layer, Path] | None`
- does: checks layers from highest to lowest precedence for the requested path
- returns: the first matching layer and path
- returns: `None` when no layer contains the requested path
- verify: count(subject="highest-precedence matching layer", equals=1)
- code: `farrier/farrier/layers.py::find_in_layers`

### method: searched_layers
- sig: `searched_layers() -> str`
- does: lists each configured layer name on its own indented line
- returns: a no-layer diagnostic when the stack is empty
- returns: the ordered layer-name listing when layers are configured
- verify: count(subject="searched layer names", equals=1)
- code: `farrier/farrier/layers.py::searched_layers`

### method: available_names
- sig: `available_names(*parts: str, suffix: str = "") -> list[str]`
- does: scans every matching layer directory for regular files
- does: filters entries by the requested suffix when one is supplied
- does: strips the suffix from returned names
- does: deduplicates names supplied by multiple layers
- returns: names sorted lexicographically
- verify: count(subject="deduplicated available names", equals=1)
- code: `farrier/farrier/layers.py::available_names`

### method: resolve_library_dir
- sig: `resolve_library_dir(cli_library: Path | None) -> Path | None`
- does: chooses the overlay candidate in flag, environment, then home-config precedence order
- raises: `SystemExit` when a selected candidate does not contain `library/`
- raises: `SystemExit` when neither an overlay nor a base library is available
- verify: count(subject="overlay resolution candidates", equals=1)
- returns: the expanded absolute overlay path when the candidate is a usable library directory
- returns: `None` when no overlay is configured but a base library is installed
- code: `farrier/farrier/layers.py::resolve_library_dir`
- tests: `farrier/tests/test_config_resolution.py::test_precedence_flag_over_env_over_config`
- tests: `farrier/tests/test_config_resolution.py::test_no_overlay_is_fine_when_base_is_installed`
- tests: `farrier/tests/test_config_resolution.py::test_bad_library_path_errors`
- tests: `farrier/tests/test_config_resolution.py::test_unresolved_errors_with_hint`

### Persisting the config-file candidate

`farrier config set-library <path>` (see [`config`](../farrier.md#config)) is how the home-config
candidate (precedence 3) gets written: it validates the path with the same `is_library_dir` check,
then calls `write_library_dir`, which persists the `library_dir` field of the
[home config file](../home-config.md) alongside any other keys already there (e.g.
`stablemate_dir`, `base_dir`).

- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_library_dir`
- detail: [config write documentation contexts](config-write-context.md)

### base_library_dir
- sig: `base_library_dir() -> Path | None`
- does: checks the explicit environment path, configured base path, configured checkout, then the cache
- does: skips invalid explicit candidates and never fetches during lookup
- returns: the resolved usable base library path, or `None`
- verify: json_path(path="$.base_library_dir", equals="/base-library")
- code: `farrier/farrier/_vendor/stablemate_core/discovery.py::base_library_dir`

### ensure_base_library_dir
- sig: `ensure_base_library_dir(*, refresh: bool = False, quiet: bool = False) -> Path | None`
- does: returns an explicit base without probing the network
- does: populates the cache when no explicit base exists
- does: refreshes an existing cache only when `refresh` is true
- returns: the resolved usable base path, or `None` when unavailable
- verify: created(subject="base library cache")
- code: `farrier/farrier/_vendor/stablemate_core/discovery.py::ensure_base_library_dir`

### cache_root
- sig: `cache_root() -> Path`
- does: uses `STABLEMATE_CACHE_DIR` when it is non-empty
- returns: the expanded shared stablemate cache directory otherwise
- verify: json_path(path="$.cache_root", matches="stablemate$")
- code: `farrier/farrier/_vendor/stablemate_core/base_cache.py::cache_root`

### cached_library_dir
- sig: `cached_library_dir() -> Path`
- does: appends `library` to the shared cache root
- returns: the cache checkout directory
- verify: json_path(path="$.cached_library_dir", matches="library$")
- code: `farrier/farrier/_vendor/stablemate_core/base_cache.py::cached_library_dir`

### fetch_allowed
- sig: `fetch_allowed() -> bool`
- does: permits fetching when `STABLEMATE_FETCH_BASE` is unset
- does: refuses fetching for `0`, `false`, `no`, or `off`, ignoring case and surrounding whitespace
- returns: whether network fetching is allowed
- verify: json_path(path="$.fetch_allowed", equals=false)
- code: `farrier/farrier/_vendor/stablemate_core/base_cache.py::fetch_allowed`

### cached_commit
- sig: `cached_commit(clone: Path | None = None) -> str | None`
- does: reads and strips the cache's `.commit` sidecar
- returns: the recorded commit, or `None` when it cannot be read or is empty
- verify: json_path(path="$.cached_commit", matches="^[0-9a-f]+$")
- code: `farrier/farrier/_vendor/stablemate_core/base_cache.py::cached_commit`

### cached_base
- sig: `cached_base() -> Path | None`
- does: validates that the cached `base-library` contains a `library/` directory
- does: never fetches
- returns: the usable cached base path, or `None`
- verify: absent(subject="network fetch during cached base lookup")
- code: `farrier/farrier/_vendor/stablemate_core/base_cache.py::cached_base`

### ensure_cached_base
- sig: `ensure_cached_base(*, quiet: bool = False) -> Path | None`
- does: returns an existing usable cache without fetching
- does: refuses fetching when `STABLEMATE_FETCH_BASE` disables network access
- does: sparse-checks out only `base-library/`, records the commit, and removes `.git`
- returns: the cached base, or `None` when unavailable
- verify: created(subject="sparse base-library cache")
- code: `farrier/farrier/_vendor/stablemate_core/base_cache.py::ensure_cached_base`

### refresh_cached_base
- sig: `refresh_cached_base(*, quiet: bool = False) -> Path | None`
- does: delegates to `ensure_cached_base` when no usable cache exists
- does: compares the cached commit with the remote `main` commit before cloning
- does: replaces the cache only after the fetched tree passes library validation
- returns: the refreshed cache, or the existing cache after a failed remote, clone, or swap
- verify: unchanged(subject="existing base cache after failed refresh")
- code: `farrier/farrier/_vendor/stablemate_core/base_cache.py::refresh_cached_base`

### is_library_dir
- sig: `is_library_dir(path: Path) -> bool`
- does: accepts a path only when its `library/` child is a directory
- does: not require `packs/` or `workflows/`
- returns: whether the path has the usable library layout
- verify: json_path(path="$.is_library_dir", equals=true)
- code: `farrier/farrier/_vendor/stablemate_core/layout.py::is_library_dir`
