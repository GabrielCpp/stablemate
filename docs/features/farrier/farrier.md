---
type: cli
slug: farrier
title: farrier — render the agent prompt library into a repository
---
# farrier — render the agent prompt library into a repository

farrier renders an agent-neutral prompt library into a target repository's Codex/Claude/Copilot
adapters, driven by that repo's `agents.yml`. It ships no library content of its own — it locates
the library directory (the `agents/` tree holding `library/`, `packs/`, `scaffolds/`, `workflows/`)
by, in order: the `--library` flag, the `$FARRIER_LIBRARY_DIR` env var, or `library_dir` in the
shared home config file (set with `farrier config set-library`). A bare `farrier [--repo DIR]`
with no recognized subcommand is treated as `install` — the dispatch/default-command rule lives in
`main`.

- binary: `farrier`
- code: `farrier/farrier/install.py::main`

**Exit codes:** `0` on success; commands raise `SystemExit(message)` on error, which propagates as
a nonzero exit with the message printed to stderr. `install --check` specifically returns `1` when
any generated file is missing or would be rewritten, `0` when the repo's generated files are
already current.

## Commands

### install
- usage: `farrier install [--repo DIR] [--config PATH] [--check] [--library DIR]` (also the
  default command: `farrier [--repo DIR] [--config PATH] [--check] [--library DIR]` when the first
  argument isn't a recognized subcommand)
- flags:
  - `--repo <dir>` — repository root to render generated files into. Default: current working
    directory.
  - `--config <path>` — path to the repo's [`agents.yml`](agents-yml-config.md) pack/workflow
    selection file. Default: `<repo>/agents.yml`.
  - `--check` — verify the repo's generated files are current without writing anything; exits `1`
    and prints which files would be rewritten if any are stale or missing, `0` otherwise.
  - `--library <dir>` — the library directory (the `agents/` tree). Overrides
    `$FARRIER_LIBRARY_DIR` and the home config's `library_dir` for this invocation.
- does:
  - run: resolve the [library directory](concepts/library-directory.md) (`--library` >
    `$FARRIER_LIBRARY_DIR` > home config) and point the module's library-content globals at it
  - run: resolve `--repo` to an absolute path; resolve the config path to `--config` if given,
    else `<repo>/agents.yml`
  - run: read [`agents.yml`](agents-yml-config.md) via `read_yaml` — `SystemExit("Missing config:
    <path>")` if `config_path` doesn't exist, else parse it with `yaml.safe_load` (an empty file
    yields `{}` rather than `None`), then `SystemExit("Config must be a YAML mapping: <path>")` if
    the parsed value isn't a `dict`
  - run: derive the install prefix (`repo.prefix` → `repo.name` → the repo dirname, kebab-cased)
    and validate `agents:` selects at least one of `codex`/`claude`/`copilot` (`normalize_agents`)
    — else `SystemExit("No agents selected in config")`
  - run: resolve the [`agents.yml`](agents-yml-config.md) selection (packs ∪ top-level
    `skills`/`prompts`/`roots`/`scaffolds`/`workflows`, minus `exclude`) against the library's
    skill/prompt/scaffold sources; `SystemExit("Selected packs did not match any skills, prompts,
    scaffolds, or workflows")` if nothing at all was selected
  - run: build a [`Renderer`](concepts/renderer.md) over the selected skills/prompts and render
    every enabled agent's skill/command files, the `roots`-driven Copilot instructions, and the
    always-on launcher scaffolding (`.agents/agents.mk`, plus `.agents/agents-context*.json` /
    `.agents/local.compose.yaml` / a thin root `Makefile` when >= 1 workflow is selected)
  - run: render each selected scaffold into its mapped or namespace-stripped destination, and each
    [`localInstructions`](agents-yml-config.md#localinstructions) entry into its target
    directories' `CLAUDE.md`/`AGENTS.md`/`CODEX.md` — together these compute the full
    `{output path: content}` map (`render_expected`) that `--check`/install below act on
  - run (`--check`): skip any output whose path is a [seed output](agents-yml-config.md#scaffolds)
    (`is_seed_output`) — a seed is never flagged missing or changed once it exists
  - run (`--check`): for each remaining expected output, record `missing: <repo-relative path>` if
    the file doesn't exist on disk, or `changed: <repo-relative path>` if its on-disk text differs
    from the expected content (both sides normalized to a single trailing newline before comparing)
  - run (`--check`): scan every directory farrier owns for files not present in the expected output
    map — `.agents/skills`, `.agents/prompts`, `.claude/skills`, `.claude/commands`,
    `.github/instructions`, `.github/prompts` (`TARGET_DIRS`), plus `.agents/workflows`; within
    `.agents/workflows`, skip files under a `__pycache__`/`.runs`/`.state`/`.codex-home` directory
    or with a `.pyc` suffix (`should_skip_workflow_file`); every remaining file not in the expected
    map is recorded `extra: <repo-relative path>`
  - run (`--check`): also record as `extra` any of these fixed paths that exist on disk but aren't
    in the expected map: `.github/copilot-instructions.md`, `.github/agents/copilot-instructions.md`,
    and the launcher scaffolding paths `.agents/agents.mk`, `.agents/local.compose.yaml`,
    `.agents/agents-context.json`
  - run (`--check`): if any `missing`/`changed`/`extra` entries were recorded, print them in that
    order (one per line, e.g. `missing: .claude/skills/foo/SKILL.md`) and return `1`; otherwise
    return `0` with no output
  - run (no `--check`): write the computed files into `--repo`, then seed `.agents/.gitignore`
    rules and a root `Makefile` `include` line when a workflow launcher was generated; print the
    count of installed files and return `0`
- code: `farrier/farrier/install.py::_run_install`

### config
- usage: `farrier config <set-library|set-stablemate|show> [args]`
- args:
  - `set-library <path>` — record `path` as `library_dir` in the home config file; errors unless
    `path` contains both a `library/` and a `packs/` directory.
  - `set-stablemate <path>` — record `path` as `stablemate_dir` in the home config file (the local
    `stablemate` checkout, used for `SRC=1` local-source runs of the generated launcher).
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
  - run (`show`): read the [home config file](home-config.md) via `read_config`; with a `key`,
    print its bare value (`SystemExit` if unset); without one, print every stored key as
    `key=value`
- code: `farrier/farrier/install.py::_run_config`

Mirrors workhorse's `config` interface (`show`/`get`/`set-library`/`set-stablemate`) so
`agents.mk` and other scripts can call either tool interchangeably for shared settings.

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
- code: `farrier/farrier/install.py::_run_source`
- verify: `farrier/tests/test_source_command.py::test_source_resolves_to_library_file`

Lets an agent go from a generated adapter under `.claude/`/`.agents/`/`.github/` back to its
editable source of truth in the library, using only the generated file's front matter.

### version
- usage: `farrier version`
- does:
  - run: print the installed `farrier` package's version (`importlib.metadata.version("farrier")`)
- code: `farrier/farrier/install.py::main`
