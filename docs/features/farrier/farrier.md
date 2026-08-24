---
type: cli
slug: farrier
title: farrier — render the agent prompt library into a repository
---
# farrier — render the agent prompt library into a repository

farrier renders an agent-neutral prompt library into a target repository's Codex/Claude/Copilot
adapters, driven by that repo's `agents.yml`. It ships no library content of its own — it renders
from a [layer stack](concepts/library-directory.md#the-layer-stack): an optional *overlay* library,
located by the `--library` flag, the `$FARRIER_LIBRARY_DIR` env var or `library_dir` in the
[shared home config file](home-config.md) (set with `farrier config set-library`), stacked above the
*base* library that ships with stablemate. Either alone is a working setup; with neither, farrier
exits with a setup hint. `farrier [--repo DIR]` with a leading flag rather than a recognized
subcommand is treated as `install`; a bare `farrier` with no arguments at all prints the top-level
help instead, the same as `farrier --help`. Both rules live in `main`.

- binary: `farrier` (the console script is declared as `farrier.install:main`, which re-exports
  `main` from `farrier.cli` — `install.py` is a compatibility facade that declares nothing of its
  own)
- code: `farrier/farrier/cli.py::main`

**Exit codes:** `0` on success; commands raise `SystemExit(message)` on error, which propagates as
a nonzero exit with the message printed to stderr. `install --check` specifically returns `1` when
any generated file is missing or would be rewritten, `0` when the repo's generated files are
already current.

## Commands

### init
- usage: `farrier init [--repo DIR] [--force]`
- flags:
  - `--repo <dir>` — repository root to write `agents.yml` into. Default: current working
    directory.
  - `--force` — replace an existing `agents.yml` instead of refusing.
- does:
  - run: resolve `--repo` to an absolute path; `SystemExit("error: <repo> is not a directory")` if
    it is not one
  - run: refuse when `<repo>/agents.yml` already exists and `--force` was not given —
    `SystemExit` naming the path, `install` as the command they probably meant, and `--force` as
    the way to overwrite anyway
  - run: render the starter config from the module template; the repo's derived name appears
    only inside a comment (spelled exactly as `repo_prefix` derives it, so the example skill name
    in that comment is the real one)
  - run: write it to `<repo>/agents.yml` and print the path plus the next step
- reads: nothing — no library resolution, no base-library fetch, no home config. It is the one
  command that runs before a repo is configured, so it must work on a machine where
  `farrier config set-library` has never been run.
- writes: `<repo>/agents.yml`, and nothing else.
- produces: [`agents.yml`](agents-yml-config.md) with `agents: {claude: true}` and an empty
  `packs:` list live, and `skills`/`prompts`/`scaffolds`/`exclude`/`template`/`workflow` present
  as commented examples. No `repo:` block: the repo's name is derived from the directory.
- code: `farrier/farrier/cli.py::_run_init`
- code: `farrier/farrier/init.py::default_config`
- verify: `farrier/tests/test_init_command.py::test_init_writes_a_config_the_installer_can_read`
- verify: `farrier/tests/test_init_command.py::test_init_refuses_to_overwrite_an_existing_config`
- verify: `farrier/tests/test_init_command.py::test_init_needs_no_library_configured`

The template is a Python string constant rather than a copy of the repo's
`farrier/agents.example.yml`: the wheel packages only the `farrier` package, so the example file
is not on disk beside an installed farrier. `agents.example.yml` stays the full reference; this is
the pruned starting point, and the two are kept consistent by hand.

### install
- usage: `farrier install [--repo DIR] [--config PATH] [--check] [--library DIR]` (also the
  default command: `farrier [--repo DIR] [--config PATH] [--check] [--library DIR]` when the first
  argument isn't a recognized subcommand)
- flags:
  - `--repo <dir>` — repository root to render generated files into. Default: current working
    directory.
  - `--config <path>` — path to the repo's [`agents.yml`](agents-yml-config.md) pack/skill
    selection file. Default: `<repo>/agents.yml`.
  - `--check` — verify the repo's generated files are current without writing anything; exits `1`
    and prints which files would be rewritten if any are stale or missing, `0` otherwise.
  - `--library <dir>` — the library directory (the `agents/` tree). Overrides
    `$FARRIER_LIBRARY_DIR` and the home config's `library_dir` for this invocation.
- does:
  - run: check out the [base library](concepts/library-directory.md#fetching-and-updating-the-base)
    before anything looks for it — `ensure_base_library_dir(refresh=not --check)` fetches it into
    `~/.cache/stablemate` when absent and updates it to the head of `main` when present. Skipped
    entirely when `$STABLEMATE_BASE_DIR`, `base_dir` or a `stablemate_dir` checkout already names
    one. `--check` passes `refresh=False`: it fetches a missing base but never updates a present
    one, because it writes nothing and runs in CI. A failed fetch is not an error here — it falls
    through to the resolution below, which raises only if there is no overlay either
  - run: resolve the [library directory](concepts/library-directory.md) (`--library` >
    `$FARRIER_LIBRARY_DIR` > home config) and point the module's library-content globals at it
  - run: resolve `--repo` to an absolute path; resolve the config path to `--config` if given,
    else `<repo>/agents.yml`
  - run: read [`agents.yml`](agents-yml-config.md) via `read_yaml` — `SystemExit("Missing config:
    <path>")` if `config_path` doesn't exist, else parse it with `yaml.safe_load` (an empty file
    yields `{}` rather than `None`), then `SystemExit("Config must be a YAML mapping: <path>")` if
    the parsed value isn't a `dict`
  - run: derive the install prefix — the repo dirname, kebab-cased (`naming.repo_prefix`); it is
    not readable from `agents.yml` — and validate `agents:` selects at least one of
    `codex`/`claude`/`copilot` (`normalize_agents`)
    — else `SystemExit("No agents selected in config")`
  - run: resolve the [`agents.yml`](agents-yml-config.md) selection (packs ∪ top-level
    `skills`/`prompts`/`roots`, minus `exclude`) against the library's skill/prompt
    sources; `SystemExit("Selected packs did not match any skills or prompts")` if
    nothing at all was selected. (The `scaffolds:` lists are collected but consumed only by the
    [`scaffold`](#scaffold) command — install renders no scaffold files.)
  - run: build a [`Renderer`](concepts/renderer.md) over the selected skills/prompts and render
    every enabled agent's skill/command files, the `roots`-driven Copilot instructions, and the
    launcher scaffolding — `.agents/agents.mk` and `.agents/agents-context*.json` for every
    repo, plus a thin root `Makefile` only when the repo has none
  - run: render each [`localInstructions`](agents-yml-config.md#localinstructions) entry into its
    target directories' `AGENTS.md` (plus a `CLAUDE.md` pointer when `claude` is enabled; every target directory must already
    exist — `SystemExit` pointing at `farrier scaffold` otherwise) — together these compute the
    full `{output path: content}` map (`render_expected`) that `--check`/install below act on
  - run (`--check`): for each expected output, record `missing: <repo-relative path>` if
    the file doesn't exist on disk, or `changed: <repo-relative path>` if its on-disk text differs
    from the expected content (both sides normalized to a single trailing newline before comparing)
  - run (`--check`): scan every directory farrier owns — `.agents/skills`, `.agents/prompts`,
    `.agents/hooks`, `.claude/skills`, `.claude/commands`, `.github/instructions`,
    `.github/prompts`, `.github/skills`, `.github/agents` (`MANAGED_DIRS`) — for files it
    [generated](#ownership) that are not in the expected output map, and record each as
    `extra: <repo-relative path>`. An **untagged** file in one of those directories is *not*
    `extra`: it is somebody's own file sitting where farrier also writes, install leaves it
    alone, and reporting it would fail `--check` with nothing to fix. Neither `.agents/workflows`
    nor `.agents/local.compose.yaml` is scanned: farrier rendered a workflow's YAML tree into the
    first and a per-workflow compose override into the second while workflows were its concern,
    and it emits neither now — so scanning them would report a leftover from an older install as
    `extra:`, a `--check` failure no re-render can fix
  - run (`--check`): also record as `extra` any of these fixed paths that exist on disk, are
    farrier's, and aren't in the expected map: `.github/copilot-instructions.md` and the
    launcher/hook scaffolding `.agents/agents.mk`, `.agents/lefthook.farrier.yml`,
    `.agents/agents-context.json`
  - run (`--check`): if any `missing`/`changed`/`extra` entries were recorded, print them in that
    order (one per line, e.g. `missing: .claude/skills/foo/SKILL.md`) and return `1`; otherwise
    return `0` with no output
  - run (no `--check`): refuse the install outright if any expected output path is held by a file
    farrier did not generate (`refuse_conflicts`) — every conflict named, nothing written, see
    [ownership](#ownership) below; otherwise delete farrier's previous output, write the computed
    files into `--repo`, then seed the managed `.gitignore` rules and a root `Makefile` `include`
    line pointing at the generated launcher; print the count of installed files and return `0`

#### ownership

Install deletes what farrier generated and nothing else. Ownership is a property of the *file*,
not of where it sits (`farrier/farrier/ownership.py`):

- a generated skill, prompt or command says so in its front matter —
  `metadata.generated_by: farrier`, see [generated-file metadata](generated-file-metadata.md);
- a generated file with nowhere to put front matter — an aggregated `AGENTS.md`/`CLAUDE.md`, the
  Copilot root instructions, `.agents/agents.mk`, a hook runner — carries the phrase
  `generated by farrier` in a comment within its first 12 lines;
- a generated `SKILL.md` owns its whole directory, so its bundled `references/` and `scripts/`
  need no mark of their own: a skill and its assets install as one unit and are removed as one;
- `.agents/local.compose.yaml` and the `.agents/agents-context*.json` manifests are owned by
  convention — JSON has no comment syntax, and a provenance key inside the object would change
  the document every reader parses.

Anything else at a managed path is somebody's own work. It survives every install, and if farrier
wants to write over it the install aborts naming the file: the two ways out — rename it, or delete
it — are the operator's to choose, not farrier's.
- code: `farrier/farrier/cli.py::_run_install`
- verify: `farrier/tests/test_base_fetch_on_install.py::test_install_refreshes_the_base`
- verify: `farrier/tests/test_base_fetch_on_install.py::test_check_fetches_but_does_not_refresh`

### config
- usage: `farrier config [--config PATH] <set-library|set-stablemate|set-base|set-worktree|show> [args]`
- flags:
  - `--config <path>` — goes **before** the action (`farrier config --config ./c.toml show`):
    the [shared config file](../workhorse/concepts/config.md)
    every config verb reads and writes, instead of the discovered one. It is written back to
    `$STABLEMATE_CONFIG` rather than threaded, because `read_config` and every writer resolve
    the path themselves — one assignment moves them together. It lets the question be asked of a
    config that is not this machine's home one (a CI file, the copy a container was launched with).
  - `show --profile <name>` — print one [`[profiles.<name>]`](../workhorse/concepts/config.md#profiles)
    table instead of the top level, flattened to one dotted line per leaf
    (`power.high.claude.model=haiku`). A profile **replaces** the top-level tables rather than
    layering over them, so what it prints is the whole config that run resolves from, and two
    profiles diff against each other line by line — that flattening is what `cat` cannot do, since
    a profile is three tables deep. A `key` given alongside it is looked up among those dotted keys
    (`show power.high.claude.model --profile cheap`). An undefined name exits with
    `UnknownProfileError`, which lists the ones the file does define. There is **no setter**: a
    profile is a nested table and `set-library`-style flat assignment cannot express one.
- args:
  - `set-library <path>` — record `path` as `library_dir` in the home config file; errors unless
    `path` contains both a `library/` and a `packs/` directory.
  - `set-stablemate <path>` — record `path` as `stablemate_dir` in the home config file (the local
    `stablemate` checkout, used for `SRC=1` local-source runs of the generated launcher).
  - `set-base <path>` — record `path` as `base_dir` in the home config file, for isolated/pipx
    installs where the `stablemate-library` wheel isn't importable; errors unless `path` contains a
    `library/` directory.
  - `set-worktree <path>` — record `path` as `worktree_dir` in the home config file: the parent
    directory new git worktrees are cut into. **No validation, not even existence** — the path names
    where worktrees will be created, so requiring it to exist would make the machine unconfigurable
    before the first worktree.
  - `show [key]` — with `key`: print that config key's bare value (error if unset). Without: print
    every config key as `key=value` lines.
- does:
  - run (`set-library`): resolve `path` to an absolute path (`~` expansion), validate it as a
    [library directory](concepts/library-directory.md) with `is_library_dir`, persist it as
    `library_dir` in the [home config file](home-config.md) via `write_library_dir`, and print
    `library_dir=<path>`
  - run (`set-stablemate`): resolve `path` to an absolute path and persist it as `stablemate_dir`
    in the [home config file](home-config.md) via `write_stablemate_dir` (no validation); print
    `stablemate_dir=<path>`
  - run (`set-base`): resolve `path` to an absolute path, validate it with `is_library_dir`,
    persist it as `base_dir` in the [home config file](home-config.md) via `write_base_dir`, and
    print `base_dir=<path>`
  - run (`set-worktree`): resolve `path` to an absolute path and persist it as `worktree_dir`
    in the [home config file](home-config.md) via `write_worktree_dir` (no validation); print
    `worktree_dir=<path>`
  - run (any action): `--config`, if given, is written into `$STABLEMATE_CONFIG` before dispatch
  - run (`show`): read the [home config file](home-config.md) via `read_config`; with `--profile`,
    narrow it with `select_profile` and flatten to dotted leaves first; with a `key`,
    print its bare value (`SystemExit` if unset, naming the profile when one was given); without
    one, print every entry as `key=value`
- code: `farrier/farrier/cli.py::_run_config`
- verify: `farrier/tests/test_config_profiles_cli.py::test_the_config_flag_reads_the_file_it_names`,
  `farrier/tests/test_config_profiles_cli.py::test_a_profile_is_shown_flattened_to_dotted_keys`,
  `farrier/tests/test_config_profiles_cli.py::test_the_profile_replaces_the_top_level_rather_than_layering_over_it`,
  `farrier/tests/test_config_profiles_cli.py::test_an_unknown_profile_exits_cleanly_and_lists_the_ones_there_are`,
  `farrier/tests/test_config_profiles_cli.py::test_set_worktree_records_a_directory_that_does_not_exist_yet`

The one command that reads and writes the [shared config file](../workhorse/concepts/config.md):
workhorse is a library and ships no `config` of its own, so `agents.mk` and other scripts go
through farrier for every shared setting. The nested `[power.<tier>.<backend>]` and
[`[profiles.<name>]`](../workhorse/concepts/config.md#profiles) tables have no writer subcommand
— they are edited by hand, and read back with `show --profile`.

### source
- usage: `farrier source <file> [--library DIR]`
- flags:
  - `--library <dir>` — library directory; overrides `$FARRIER_LIBRARY_DIR` and the home config
    (same resolution precedence as `install`).
- args:
  - `<file>` — path to a farrier-generated `SKILL.md` or command `.md` file. Required.
- does:
  - run: resolve `<file>` to an absolute path; `SystemExit` if it is not a file
  - run: read `<file>`'s YAML front matter and parse its
    [`metadata:` block](generated-file-metadata.md) via `frontmatter_metadata`, extracting the
    `source` field (a library-anchored, machine-independent path stamped in by `install`'s
    generated-file provenance banner)
  - run: `SystemExit` if `source` is absent (`<file>` is not a farrier-generated skill/command)
  - run: resolve the [library directory](concepts/library-directory.md) the same way `install`
    does (`--library` > `$FARRIER_LIBRARY_DIR` > home config), then join `source` under it and
    resolve to an absolute path
  - run: `SystemExit` if the resolved source is not a file (the library moved or renamed it since
    the file was generated); otherwise print the resolved absolute path
- code: `farrier/farrier/cli.py::_run_source`
- verify: `farrier/tests/test_source_command.py::test_source_resolves_to_library_file`

Lets an agent go from a generated adapter under `.claude/`/`.agents/`/`.github/` back to its
editable source of truth in the library, using only the generated file's front matter.

### scaffold
- usage: `farrier scaffold [<id>] [--param KEY=VALUE]... [--repo DIR] [--list] [--library DIR]`
- flags:
  - `<id>` — the scaffold definition id to apply. Omitted (or with `--list`): print the scaffolds
    available to `--repo` with their params/defaults and exit `0`.
  - `--param KEY=VALUE` — set a scaffold parameter (repeatable). Unknown keys error listing the
    accepted params; a declared param with a `~`/null default is required.
  - `--repo <dir>` — repository root to scaffold into. Default: current working directory.
  - `--library <dir>` — same resolution override as `install`.
- does:
  - run: resolve the [library directory](concepts/library-directory.md) and load every scaffold
    definition from the library's `scaffolds/*.yml`/`*.yaml` files (`load_scaffold_defs`) — each
    file maps scaffold ids to `{description?, params?, tree}`; a duplicate id across files or a
    definition without a `tree:` mapping is a `SystemExit`
  - run: compute the repo's catalog (`available_scaffold_ids`): with a `<repo>/agents.yml`, the
    union of its `scaffolds:` list and every selected pack's `scaffolds:` list (ids must be plain
    strings — the legacy `{source-prefix: dest}` mapping form errors with a migration hint,
    `parse_scaffold_ids`); with no `agents.yml` (bootstrapping a fresh repo), every library id
  - run: `SystemExit` when `<id>` is not defined in the library (lists the defined ids) or not in
    the repo's catalog (points at the `agents.yml` `scaffolds:` list)
  - run: resolve params (`resolve_scaffold_params`): declared defaults overlaid with `--param`
    values, plus built-ins `repo_name` (kebab-cased `--repo` dirname) and `repo_title`
    (title-cased words) unless shadowed
  - run: flatten the definition's `tree:` (`flatten_scaffold_tree`) — a string value is inline
    file content, a `{url: ...}` mapping is downloaded at write time (30s timeout, `SystemExit`
    on failure), any other mapping is a nested sub-tree, and a null value (bare `dir:` key) or
    empty mapping is an empty directory (created and reported like files, `created:`/`exists
    (kept):` with a trailing `/`); substitute `$param` placeholders strictly in each path
    (unknown param or a path
    escaping the repo is a `SystemExit`) and leniently (`safe_substitute`) in inline content
  - run: write each file that does not already exist (`created: <rel>`) and keep any that does
    (`exists (kept): <rel>`) — every scaffolded file is a seed the repo owns after first write;
    re-running is always a no-op for existing files; print a summary count and return `0`
- code: `farrier/farrier/cli.py::_run_scaffold`
- verify: `farrier/tests/test_scaffold_command.py::test_scaffold_writes_tree_with_defaults`

Lets an agent stand up a new repo or service folder from the library's parameterized scaffold
definitions (per-stack `.gitignore` seeds, the standard `docs/` hierarchy) instead of hand-writing
boilerplate — placement folders are `--param` values, never baked into the library.

### version
- usage: `farrier version`
- does:
  - run: print the installed `farrier` package's version (`importlib.metadata.version("farrier")`)
- code: `farrier/farrier/cli.py::main`
