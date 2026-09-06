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
help instead, the same as `farrier --help`. Both rules live in `main`. Repository installs also
refresh [QA-evidence ignore rules](concepts/qa-evidence-ignore-rules.md) when they render the
staged-files gate.

- binary: `farrier` (the console script is declared as `farrier.install:main`, which re-exports
  `main` from `farrier.cli` — `install.py` is a compatibility facade that declares nothing of its
  own)
- code: `farrier/farrier/cli.py::main`
- detail: [hook manager wiring](concepts/hook-manager-wiring.md)
- detail: [QA-evidence ignore rules](concepts/qa-evidence-ignore-rules.md)
- detail: [selection error reporting](concepts/selection-errors.md)
- detail: [vendored core package](concepts/vendored-core-package.md)
- detail: [drift report](concepts/drift-report.md)
- detail: [repository diagnosis](concepts/doctor-diagnosis.md)
- detail: [library front-matter check](concepts/library-frontmatter-check.md)
- detail: [front-matter parsing](concepts/frontmatter-parsing.md)
- detail: [library view](concepts/library-view.md)
- detail: [output installation](concepts/output-installation.md)
- detail: [output cleanup](concepts/output-cleanup.md)
- detail: [scaffold operations](concepts/scaffold-operations.md)
- detail: [template values](concepts/template-values.md)
- detail: [user library](concepts/user-library.md)
- detail: [CLI internals](concepts/cli-internals.md)
- detail: [compatibility facade](concepts/compatibility-facade.md)
- detail: [runtime clock](concepts/runtime-clock.md)
- detail: [initialize and render repository](flows/initialize-and-render-repository.md)
- detail: [inspect and maintain library](flows/inspect-and-maintain-library.md)
- detail: [verify and repair generated outputs](flows/verify-and-repair-generated-outputs.md)
- detail: [Farrier CLI and Make drivers](ops/farrier-cli-and-make-drivers.md)

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
  - run: resolve `--repo` to an absolute path
  - run: raise `SystemExit("error: <repo> is not a directory")` when the resolved path is not a
    directory
  - run: refuse to replace an existing `<repo>/agents.yml` unless `--force` was given
  - run: name the existing path in the refusal, recommend `install`, and identify `--force` as
    the explicit replacement option
  - run: render the starter config from the module template
  - run: place the repo's derived name only inside a comment
  - run: spell the example skill name exactly as `repo_prefix` derives it
  - run: write the rendered config to `<repo>/agents.yml`
  - run: print the written path
  - run: print `Next: list the packs you want under packs:, then farrier install.`
- verify: json_path(path="$.agents.claude", equals=true)
- verify: json_path(path="$.repo", absent=true)
- verify: unchanged(subject="<repo>/agents.yml")
- verify: created(subject="<repo>/agents.yml")
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `farrier/farrier/cli.py::_run_init`
- code: `farrier/farrier/init.py::default_config`
- tests: `farrier/tests/test_init_command.py::test_init_writes_a_config_the_installer_can_read`
- tests: `farrier/tests/test_init_command.py::test_init_refuses_to_overwrite_an_existing_config`
- tests: `farrier/tests/test_init_command.py::test_init_needs_no_library_configured`
- reads: nothing — no library resolution, no base-library fetch, no home config. It is the one
  command that runs before a repo is configured, so it must work on a machine where
  `farrier config set-library` has never been run.
- writes: `<repo>/agents.yml`, and nothing else.
- produces: [`agents.yml`](agents-yml-config.md) with `agents: {claude: true}` and an empty
  `packs:` list live, and `skills`/`prompts`/`scaffolds`/`exclude`/`template`/`workflow` present
  as commented examples. No `repo:` block: the repo's name is derived from the directory.

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
- verify: unchanged(subject="repository after an install --check run")
- does:
  - run: check out the [base library](concepts/library-directory.md#fetching-and-updating-the-base)
    by calling `ensure_base_library_dir(refresh=not --check)`
  - verify: created(subject="base library checkout used for install")
  - run: check out the base library before anything looks for it
  - verify: created(subject="generated output from a base library fetched before layer resolution")
  - run (base absent): fetch the base library into `~/.cache/stablemate`
  - verify: created(subject="previously absent base library cache")
  - run (cached base present): update the base library to the head of `main`
  - verify: persists(subject="base library cache after install refresh")
  - run (configured base): skip fetching and updating when `$STABLEMATE_BASE_DIR`, `base_dir` or a
    `stablemate_dir` checkout already names the base library
  - verify: unchanged(subject="configured base library directory")
  - run (`--check`, base absent): pass `refresh=False`, which fetches the base library into the cache
  - verify: created(subject="base library cache during --check")
  - run (`--check`, cached base present): pass `refresh=False` to leave the cache at its current
    revision, because the check writes nothing and runs in CI
  - verify: unchanged(subject="present base library cache during --check")
  - verify: unchanged(subject="existing base library cache during --check")
  - run (failed fetch): continue to library resolution, which raises only if there is no overlay
    either
  - verify: created(subject="generated output from the overlay after a failed base fetch")
  - run: resolve the [library directory](concepts/library-directory.md) (`--library` >
    `$FARRIER_LIBRARY_DIR` > home config) and point the module's library-content globals at it
  - verify: created(subject="generated output from the highest-precedence resolved library layer")
  - run: resolve `--repo` to an absolute path used as the generated-output root
  - verify: created(subject="expected generated output under the resolved --repo path")
  - run: resolve the config path to `--config` if given, else `<repo>/agents.yml`
  - verify: created(subject="generated output selected by the resolved config path")
  - run: read [`agents.yml`](agents-yml-config.md) via `read_yaml` — `SystemExit("Missing config:
    <path>")` if `config_path` doesn't exist, else parse it with `yaml.safe_load` (an empty file
    yields `{}` rather than `None`), then `SystemExit("Config must be a YAML mapping: <path>")` if
    the parsed value isn't a `dict`
  - verify: count(subject="stderr lines equal to Config must be a YAML mapping: <path>", equals=1)
  - run: derive the install prefix from the kebab-cased repo dirname (`naming.repo_prefix`), never
    from `agents.yml`
  - verify: created(subject="generated output bearing the repo-derived install prefix")
  - run: validate that `agents:` selects at least one of `codex`/`claude`/`copilot`
    (`normalize_agents`), else raise `SystemExit("No agents selected in config")`
  - verify: exit_status(code=1)
  - run: resolve the [`agents.yml`](agents-yml-config.md) selection (packs ∪ top-level
    `skills`/`prompts`/`roots`, minus `exclude`) against the library's skill/prompt sources. The
    `scaffolds:` lists are collected but consumed only by the [`scaffold`](#scaffold) command, so
    install renders no scaffold files
  - verify: created(subject="generated output selected by agents.yml")
  - run: raise `SystemExit("Selected packs did not match any skills or prompts")` when the
    selection contains no skills or prompts
  - verify: exit_status(code=1)
  - run: render every enabled agent's selected skill files through a
    [`Renderer`](concepts/renderer.md)
  - verify: created(subject="enabled agents' selected skill files")
  - run: render every enabled agent's selected command files through the `Renderer`
  - verify: created(subject="enabled agents' selected command files")
  - run: render the `roots`-driven Copilot instructions through the `Renderer`
  - verify: created(subject="roots-driven Copilot instructions")
  - run: render `.agents/agents.mk` for every repository
  - verify: created(subject=".agents/agents.mk")
  - run: render `.agents/agents-context*.json` for every repository
  - verify: created(subject=".agents/agents-context*.json manifests")
  - run: render a thin root `Makefile` only when the repository has none
  - verify: created(subject="thin root Makefile in a repository that had none")
  - run: render each [`localInstructions`](agents-yml-config.md#localinstructions) entry into its
    target directories' `AGENTS.md` as part of the full `{output path: content}` map
    (`render_expected`) that `--check` or install acts on
  - verify: created(subject="localInstructions AGENTS.md output")
  - run: render a `CLAUDE.md` pointer for each local-instructions target when `claude` is enabled
  - verify: created(subject="localInstructions CLAUDE.md pointer")
  - run: raise `SystemExit` pointing at `farrier scaffold` when a local-instructions target
    directory does not already exist
  - verify: exit_status(code=1)
  - run (`--check`): for each expected output, record `missing: <repo-relative path>` if
    the file doesn't exist on disk, or `changed: <repo-relative path>` if its on-disk text differs
    from the expected content (both sides normalized to a single trailing newline before comparing)
  - verify: count(subject="--check drift lines for output differing only in trailing-newline count", equals=0)
  - run (`--check`): scan `MANAGED_DIRS` for [generated](#ownership) files absent from the expected
    output map, recording each as `extra: <repo-relative path>`
  - verify: count(subject="generated files absent from the expected output map", equals=1)
  - run (`--check`): leave an untagged file in a managed directory alone instead of reporting it as
    `extra`, because it is somebody's own file and an install cannot fix it
  - verify: unchanged(subject="untagged file in a managed directory")
  - run (`--check`): omit `.agents/workflows` from the scan because Farrier no longer emits its
    legacy workflow YAML tree, so a reported leftover could not be fixed by re-rendering
  - verify: omits(subject="--check extra report", matches="^extra: \\.agents/workflows/")
  - run (`--check`): omit `.agents/local.compose.yaml` from the scan because Farrier no longer
    emits the legacy per-workflow compose override
  - verify: omits(subject="--check extra report", text="extra: .agents/local.compose.yaml")
  - run (`--check`): keep `.github/instructions` in `MANAGED_DIRS` so a later install reports the
    per-skill `<name>.instructions.md` copies tagged by an older install
  - verify: count(subject="obsolete generated .github/instructions copies", equals=1)
   - run (`--check`): also record as `extra` every existing Farrier-owned fixed path absent from
     the expected map: `.github/copilot-instructions.md`, `.agents/agents.mk`,
     `.agents/lefthook.farrier.yml`, `.agents/agents-context.json`
  - verify: count(subject="fixed-path extras absent from the expected output map", equals=4)
  - run (`--check`): if any `missing`/`changed`/`extra` entries were recorded, print them in that
    order, one per line, such as `missing: .claude/skills/foo/SKILL.md`
  - verify: count(subject="ordered missing, changed, and extra stdout lines", equals=3)
  - run (`--check`): return `1` when any `missing`/`changed`/`extra` entries were recorded
  - verify: exit_status(code=1)
  - run (`--check`): produce no output when no drift entries were recorded
  - verify: omits(subject="stdout", matches=".+")
  - run (`--check`): return `0` when no drift entries were recorded
  - verify: exit_status(code=0)
  - run (no `--check`): refuse the install through `refuse_conflicts` when an expected output path
    is held by a file Farrier did not generate, according to the [ownership](#ownership) contract
  - verify: exit_status(code=1)
  - run (no `--check`): name every unowned output conflict in the refusal
  - verify: count(subject="unowned output conflicts named in the refusal", equals=2)
  - run (no `--check`): write nothing after detecting an unowned output conflict
  - verify: unchanged(subject="repository after an unowned-output conflict")
  - run (no `--check`): perform the conflict scan before deleting any prior output
  - verify: unchanged(subject="repository before the conflict scan succeeds")
  - run (no `--check`): when a path is unowned, abort with every conflicting repo-relative path
    and leave the repository unchanged
  - verify: unchanged(subject="repository after an unowned-output conflict")
  - run (no `--check`): remove only Farrier-owned output files under the managed directories and
    files
  - verify: removed(subject="previously existing deselected Farrier-owned output file")
  - run (no `--check`): remove empty directories left by Farrier-owned output deletion
  - verify: removed(subject="previously existing empty directory left by deselected Farrier-owned output")
  - run (no `--check`): delete the convention-owned legacy `.agents/local.compose.yaml` when it is
    present, even though current rendering no longer produces it
  - verify: removed(subject="previously existing legacy .agents/local.compose.yaml")
  - run (no `--check`): leave untagged neighboring files in place during removal
  - verify: unchanged(subject="untagged neighboring output")
  - run (no `--check`): write expected outputs in repo-relative path order
  - verify: created(subject="expected generated output")
  - run (no `--check`): normalize ordinary output to one trailing newline
  - verify: count(subject="trailing newlines in ordinary generated output", equals=1)
  - run (no `--check`): preserve executable permission for executable content
  - verify: exit_status(code=0)
  - run (no `--check`): when `.agents/agents.mk` is among the outputs, refresh the managed
    `.agents/` ignore rules
  - verify: persists(subject="managed .agents ignore rules")
  - run (no `--check`): when `.agents/agents.mk` is among the outputs and a root `Makefile` exists,
    append the launcher include without replacing the existing file
  - verify: persists(subject="root Makefile launcher include")
  - run (no `--check`): when the generated staged-files gate is among the outputs and repo
    scaffolding is enabled, refresh the QA-evidence ignore rules
  - verify: persists(subject="QA-evidence ignore rules")
  - run (no `--check`): when a hook manager is supplied, splice Farrier's fenced hook entry after
    all generated files have been written
  - verify: persists(subject="hook-manager fenced entry")
  - run (no `--check`): when the supplied hook manager is `none`, remove Farrier's existing fenced
    hook entry from each supported manager file instead of adding a new entry
  - verify: removed(subject="previously existing Farrier fenced hook entry for the disabled hook manager")
  - run (no `--check`): when `managed.repo_scaffolding` is false, skip the QA-evidence ignore
    rules because the user-home install scope supplies no repository launcher output or hook manager
  - verify: unchanged(subject="user-home QA-evidence ignore rules")
  - code: `farrier/farrier/outputs.py::install_outputs`
  - tests: `farrier/tests/test_tagged_deletion.py::test_an_untagged_file_at_an_output_path_aborts_the_whole_install`
  - tests: `farrier/tests/test_tagged_deletion.py::test_a_deselected_skill_is_still_removed`
  - tests: `farrier/tests/test_qa_evidence_ignore.py::test_the_install_follows_the_skill_that_ships_the_gate`
  - tests: `farrier/tests/test_makefile_include.py::test_appends_include_block_and_preserves_existing`
  - tests: `farrier/tests/test_hook_managers.py::test_every_manager_gets_the_command_and_keeps_the_users_lines`
- detail: [hook manager wiring](concepts/hook-manager-wiring.md)
  - run (no `--check`): when the supplied hook manager is `none`, remove Farrier's existing fenced
    hook entry from each supported manager file instead of adding a new entry

#### ownership

Install deletes what farrier generated and nothing else. The
[installation output ownership](concepts/installation-output-ownership.md) contract makes
ownership a property of the *file*, not of where it sits (`farrier/farrier/ownership.py`):

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

### install---user
- usage: `farrier install --user [--check] [--home DIR] [--library DIR]`
- flags:
  - `--user` — install into the harness home directories instead of a repo. Selection comes from
    the [shared config file](../workhorse/concepts/config.md), not from an `agents.yml`; no repo
    is read and none is written to.
  - `--home <dir>` — the home directory to install into. Default: `~`. It exists for tests and
    for a container that keeps its agent config somewhere other than `$HOME`.
  - `--check` — as for a repo install: verify the installed files are current, write nothing,
    exit `1` naming what would be rewritten.
  - `--library <dir>` — the same [layer resolution](concepts/library-directory.md) a repo install
    uses. User scope changes *where files land*, never where sources come from.
- does:
  - run: read `[user_library.<harness>]` from the config — one table per harness that gets a
    personal library, holding the same `skills:`/`prompts:`/`exclude:` keys
    [`agents.yml`](agents-yml-config.md) uses. A harness with no table installs nothing
  - verify: count(subject="user-scope outputs for an unconfigured harness", equals=0)
  - run: no user-library table at all is an error naming the config path, since `--user` was
    asked for explicitly
  - verify: exit_status(code=1)
  - run: render each table's selection with a [`Renderer`](concepts/renderer.md) at user scope
    into `~/.claude/skills/<name>/SKILL.md`, `~/.claude/commands/<name>.md`,
    `~/.codex/skills/<name>/SKILL.md` and `~/.copilot/skills/<name>/SKILL.md`
  - run: name each installed skill by its **library group** (`stablemate/ostler` →
    `stablemate-ostler`), never by a repo — there is no repo to prefix with, and a personal skill
    is the same skill in every checkout
  - run: substitute `{{ template.* }}` from the shared `[user_library.template]` table
  - verify: persists(subject="user-scope skill rendered with shared template values")
  - run: treat a template value as a fact about the machine rather than the harness reading it, so
    the value is not configured per harness
  - verify: persists(subject="shared user-library template configuration")
  - run: reject an undefined `{{ template.* }}` reference as a hard error rather than rendering it
    empty
  - verify: exit_status(code=1)
  - run: reject any `{{ repo.* }}` reference as a hard error because user scope has no repository
    to supply it
  - verify: exit_status(code=1)
  - run: `prompts:` under any harness but `claude` is a hard error — Claude alone has a personal
    command directory. A silent skip would be a prompt the agent never sees and nobody misses
  - run: write **no repo scaffolding** — no launcher, no `.agents/` context manifest, no
    `.gitignore` rules, no aggregated `AGENTS.md`. Each of those describes a checkout
  - run: [ownership](#ownership) is unchanged, so a hand-written `~/.claude/skills/mine/SKILL.md`
    survives every install and a path farrier would overwrite aborts the run naming the file
- **Never implied by a repo install.** The two scopes collide differently per harness — a personal
  Claude skill shadows the project's copy, while Copilot resolves the project's first — so which
  copy an agent gets depends on the harness. That is a decision for the operator to take once,
  explicitly, rather than a side effect of installing into some repo.
- code: `farrier/farrier/cli.py::_run_user_install`, `farrier/farrier/outputs.py::render_user_expected`
- verify: created(subject="selected user-scope harness outputs")
- verify: absent(subject="repo scaffolding in the user home")
- verify: removed(subject="deselected user-scope generated outputs")
- verify: unchanged(subject="hand-written user-home skill")
- tests: `farrier/tests/test_user_install.py::test_skills_and_prompts_land_in_the_harness_home`
- tests: `farrier/tests/test_user_install.py::test_the_repo_scaffolding_stays_out_of_the_home`
- tests: `farrier/tests/test_user_install.py::test_a_deselected_skill_is_swept_and_a_hand_written_one_is_not`

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
  - run (`show`): read the [home config file](home-config.md) via `read_config`
  - run (`show --profile`): narrow the config with `select_profile` and flatten it to dotted
    leaves first
  - run (`show <key>`): print the key's bare value
  - run (`show <key>`): `SystemExit` if the key is unset, naming the profile when one was given
  - run (`show`): without a key, print every entry as `key=value`
- verify: omits(subject="selected profile output", text="power.high.claude.model=opus")
- code: `farrier/farrier/cli.py::_run_config`
- tests: `farrier/tests/test_config_profiles_cli.py::test_the_config_flag_reads_the_file_it_names`,
   `farrier/tests/test_config_profiles_cli.py::test_a_profile_is_shown_flattened_to_dotted_keys`,
   `farrier/tests/test_config_profiles_cli.py::test_the_profile_replaces_the_top_level_rather_than_layering_over_it`,
   `farrier/tests/test_config_profiles_cli.py::test_an_unknown_profile_exits_cleanly_and_lists_the_ones_there_are`,
   `farrier/tests/test_config_profiles_cli.py::test_set_worktree_records_a_directory_that_does_not_exist_yet`

The one command that reads and writes the [shared config file](../workhorse/concepts/config.md):
workhorse is a library and ships no `config` of its own, so `agents.mk` and other scripts go
through farrier for every shared setting. The nested `[power.<tier>.<backend>]` and
[`[profiles.<name>]`](../workhorse/concepts/config.md#profiles) tables have no writer subcommand
— they are edited by hand, and read back with `show --profile`.

### library
- usage: `farrier library list|show|check [--library DIR] [--layer base|overlay]`
- flags:
  - `--library <dir>` — same resolution override as `install`
  - `--<kind>s` (`--skills`, `--prompts`, `--policies`, `--packs`, `--scaffolds`, `--roots`) —
    `list` only; repeatable, and reporting every kind is the default
  - `--<kind>` (`--skill NAME`, `--prompt NAME`, …) — `show` only; exactly one is required
  - `--layer base|overlay` — narrow to one layer. Shorthand rather than a path, so the same
    command means the same thing on the next machine.
  - `--strict` — `check` only; treat warnings (untagged skills, fragile unquoted values) as errors
  - `--check` — the older spelling of `library check`, kept working
- args:
  - `list` — print the catalog of what the resolved layer stack provides
  - `show` — print one item's library source, as written
  - `check` — report front-matter problems in the library's own sources
- does:
  - run: resolve the [library directory](concepts/library-directory.md) into the active layer stack
  - run: raise `SystemExit` when both configuration and an installed base library are absent
  - run (`list`): print the layer stack
  - run (`list`): print one block for each selected kind
  - run (`list`): print each item's library id
  - run (`list`): print each item's installed name
  - run (`list`): print the layer each item resolves from
  - run (`list`): print the layers each item shadows
  - run (`list`): report one layer when base and overlay name the same directory, so a repo that
    pins its own tree as both does not report it as shadowing itself
  - run (`list --layer`): report what that layer **provides**, including items the other layer
    shadows — filtering on the winner would answer a different question than the one asked
  - run (`show`): resolve NAME by library id, then installed name, then bare basename
  - run (`show`): when a bare basename matches more than one item, refuse it with every matching
    full library id
  - run (`show`): when NAME is unknown, refuse it with the full library-id catalog
  - run (`show`): print the selected source file verbatim, so the output pipes
  - run (`check`): run `check_library` over each layer's `library/` root and print the findings
  - run (`check`): return `1` on any error (or any warning under `--strict`)
- verify: exit_status(code=0)
- verify: count(subject="resolved library layers", equals=1)
- verify: exit_status(code=1)
- verify: count(subject="library list layer headers containing '# layer:'", equals=2)
- verify: count(subject="library list blocks for selected kinds", equals=1)
- verify: count(subject="library ids in the selected kind block", equals=1)
- verify: count(subject="installed names in the selected kind block", equals=1)
- verify: count(subject="resolving layer labels in the selected kind block", equals=1)
- verify: count(subject="'shadows' annotations on the library list row for stacks/api", equals=1)
- verify: count(subject="library list layer headers for an identical base and overlay", equals=1)
- verify: count(subject="items provided by the selected library layer", equals=1)
- verify: count(subject="library show name resolution result", equals=1)
- verify: exit_status(code=1)
- verify: count(subject="full library ids in the ambiguous-basename refusal", equals=2)
- verify: exit_status(code=1)
- verify: count(subject="full library ids in the unknown-name catalog", equals=3)
- verify: count(subject="bytes differing between library show output and the selected source", equals=0)
- verify: count(subject="library front-matter findings reported", equals=1)
- verify: exit_status(code=1)
- code: `farrier/farrier/cli.py::_run_library`, `farrier/farrier/library_view.py`
- tests: `farrier/tests/test_library_browse.py::test_a_shadowed_item_is_reported_as_shadowed`

Ownership of a name belongs to whichever layer wins it, and nothing in a rendered repo says
which one did. `list` is where that becomes visible before it becomes a surprise, and `show`
prints the copy that would actually be installed — the reverse of `farrier source`, which walks
from a generated file back to the library.

### source
- usage: `farrier source <file> [--library DIR]`
- flags:
  - `--library <dir>` — library directory; overrides `$FARRIER_LIBRARY_DIR` and the home config
    (same resolution precedence as `install`).
- args:
  - `<file>` — path to a farrier-generated `SKILL.md` or command `.md` file. Required.
- does:
  - run: resolve `<file>` to an absolute path
  - run: `SystemExit` if `<file>` is not a file
  - run: read `<file>`'s YAML front matter and parse its
     [`metadata:` block](generated-file-metadata.md) via `frontmatter_metadata`, extracting the
     `source` field (a library-anchored, machine-independent path stamped in by `install`'s
     generated-file provenance banner)
  - run: `SystemExit` if `source` is absent (`<file>` is not a farrier-generated skill/command)
  - run: resolve the [library directory](concepts/library-directory.md) the same way `install`
    does (`--library` > `$FARRIER_LIBRARY_DIR` > home config), then join `source` under it and
    resolve to an absolute path
  - run: `SystemExit` if the resolved source is not a file because the library moved or renamed it
    since the file was generated
  - run: print the resolved absolute path
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_run_source`
- code: `farrier/farrier/frontmatter.py::frontmatter_metadata`
- tests: `farrier/tests/test_source_command.py::test_source_resolves_to_library_file`
- tests: `farrier/tests/test_source_command.py::test_frontmatter_metadata_reads_nested_block`
- tests: `farrier/tests/test_source_command.py::test_frontmatter_metadata_empty_without_block`

Lets an agent go from a generated adapter under `.claude/`/`.agents/`/`.github/` back to its
editable source of truth in the library, using only the generated file's front matter.
`frontmatter_metadata` is declared in the frontmatter parser; `install.py` only re-exports it as
a compatibility facade.

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
  - run: resolve the [library directory](concepts/library-directory.md), then load every scaffold
    definition from its `scaffolds/*.yml`/`*.yaml` files (`load_scaffold_defs`)
  - run: interpret each scaffold file as ids mapped to `{description?, params?, tree}` definitions
  - run: raise `SystemExit` when two files in one layer define the same scaffold id
  - run: raise `SystemExit` when a scaffold definition is not a mapping with a `tree:` mapping
  - run: with `<repo>/agents.yml`, compute the repo's catalog (`available_scaffold_ids`) as the
    union of its `scaffolds:` list plus every selected pack's `scaffolds:` list
  - run: reject non-string catalog entries, including the legacy `{source-prefix: dest}` mapping
    form, with a migration hint from `parse_scaffold_ids`
  - run: with no `agents.yml`, expose every library scaffold id to bootstrap a fresh repo
  - run: raise `SystemExit` for an `<id>` absent from the library, listing the defined ids
  - run: raise `SystemExit` for an `<id>` absent from the repo's catalog, pointing at the
    `agents.yml` `scaffolds:` list
  - run: resolve params (`resolve_scaffold_params`): declared defaults overlaid with `--param`
    values, plus built-ins `repo_name` (kebab-cased `--repo` dirname) and `repo_title`
    (title-cased words) unless shadowed
  - run: flatten string values in the definition's `tree:` into inline file content
  - run: download a `{url: ...}` file value at write time with a 30-second timeout
  - run: raise `SystemExit` when a URL-backed scaffold file cannot be downloaded
  - run: recursively flatten mapping values that are nested sub-trees
  - run: create a null tree value or empty mapping as an empty directory
  - run: report an empty directory as `created: <rel>/` or `exists (kept): <rel>/`
  - run: substitute `$param` placeholders strictly in each scaffold path
  - run: raise `SystemExit` when a path contains an unknown parameter or escapes the repo
  - run: substitute parameters leniently (`safe_substitute`) in inline file content
  - run: write each file absent from the target repo, reporting `created: <rel>`
  - run: preserve each existing target file, reporting `exists (kept): <rel>`
  - run: treat every scaffolded file as a seed the repo owns after its first write
  - run: make every re-run a no-op for existing files
  - run: print the number of files created by this invocation
  - run: return `0` after scaffolding completes
- verify: count(subject="loaded scaffold definitions", equals=1)
- verify: count(subject="definitions loaded from one scaffold file", equals=1)
- verify: exit_status(code=1)
- verify: exit_status(code=1)
- verify: count(subject="available scaffold ids from agents.yml and a selected pack", equals=2)
- verify: exit_status(code=1)
- verify: count(subject="available scaffold ids without agents.yml", equals=1)
- verify: exit_status(code=1)
- verify: exit_status(code=1)
- verify: count(subject="resolved scaffold parameters", equals=1)
- verify: created(subject="api/.gitignore from inline scaffold content")
- verify: created(subject=".gitignore from a URL-backed scaffold file")
- verify: exit_status(code=1)
- verify: created(subject="api/docs/README.md from a nested scaffold tree")
- verify: created(subject="api/logs empty scaffold directory")
- verify: count(subject="status line for an empty scaffold directory", equals=1)
- verify: created(subject="backend/.gitignore selected by the dir parameter")
- verify: exit_status(code=1)
- verify: persists(subject="inline scaffold content containing literal dollar expressions")
- verify: created(subject="api/.gitignore")
- verify: unchanged(subject="existing api/.gitignore")
- verify: unchanged(subject="scaffolded file edited after its first write")
- verify: unchanged(subject="existing files after a scaffold re-run")
- verify: count(subject="files reported as created by a one-file scaffold", equals=1)
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_run_scaffold`
- tests: `farrier/tests/test_scaffold_command.py::test_scaffold_writes_tree_with_defaults`

Lets an agent stand up a new repo or service folder from the library's parameterized scaffold
definitions (per-stack `.gitignore` seeds, the standard `docs/` hierarchy) instead of hand-writing
boilerplate — placement folders are `--param` values, never baked into the library.

### version
- usage: `farrier version`
- does:
  - run: print the installed `farrier` package's version (`importlib.metadata.version("farrier")`)
- verify: count(subject="stdout lines equal to the installed farrier package version", equals=1)
- code: `farrier/farrier/cli.py::main`

### workflows
- usage: `farrier workflows [--names]`
- flags:
  - `--names` — print only the sorted, space-separated workflow names for the generated
    [make launcher](concepts/generated-agent-launcher.md)
- does:
  - discover installed workflow distributions from `pipx list --json`
  - when `--names` is given, print the discovered workflow names on one line
  - when `--names` is given, sort the names alphabetically
  - when `--names` is given, print a duplicate workflow name only once
  - when `--names` is given and no workflow is discoverable, print an empty line
  - without `--names`, print each provider's distribution name
  - without `--names`, print each provider's version
  - without `--names`, print each provider's origin
  - without `--names`, print each provider's workflow names as indented lines
  - without `--names` and with no discoverable workflows, print guidance to install a workflow
    distribution
  - without `--names`, mark a provider whose local source directory is missing with
    `** source directory is gone **`
- errors:
  - treat a missing `pipx` executable as an empty discoverable workflow set
  - treat a nonzero `pipx list --json` result as an empty discoverable workflow set
  - treat malformed `pipx list --json` output as an empty discoverable workflow set
- exits:
  - return `0` for successful discovery output
  - return `0` for an empty `--names` result
  - return `1` in human-readable mode when any discovered provider has a missing local source
    directory
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- verify: count(subject="space-separated workflow names", equals=2)
- verify: count(subject="deduplicated workflow names", equals=1)
- code: `farrier/farrier/cli.py::_run_workflows`
- detail: [generated agent launcher](concepts/generated-agent-launcher.md)
- detail: [installed workflow discovery](concepts/installed-workflow-discovery.md)
- tests: `farrier/tests/test_pipx.py::test_discover_reads_the_json_pipx_actually_emits`
- tests: `farrier/tests/test_pipx.py::test_pipx_not_installed_means_no_workflows_not_a_broken_build`
- tests: `farrier/tests/test_pipx.py::test_pipx_failing_or_emitting_junk_means_no_workflows`
- tests: `farrier/tests/test_launcher_make.py::test_a_discovered_workflow_becomes_a_real_target`

### doctor
- usage: `farrier doctor [--repo DIR]`
- flags:
  - `--repo <dir>` — repository root whose `agents.yml` is diagnosed. Default: current working
    directory.
- does:
  - run: resolve the supplied repository path through `doctor.report`
  - run: report an error when `<repo>/agents.yml` is absent
  - run: report an error when `agents.yml` cannot be read or parsed as YAML
  - run: report an error when the parsed `agents.yml` value is not a mapping
  - run: warn when `workspace.service_roots` is empty
  - run: warn when `workspace.service_markers` is empty
  - run: warn when no top-level `services:` mapping or `workflow.services:` mapping exists
  - run: warn when a service entry is not a mapping
  - run: warn when a declared service omits a `lint` or `test` command, while accepting the
    legacy top-level `lint` mapping as a lint declaration
  - run: warn when a workspace service root matches neither a service key nor its complete root
    path
  - run: print each finding with its severity and operator-facing message
  - run: print an error and warning count summary when findings exist
- exits:
  - return `0` for a readable mapping, including when it has warnings
  - return `1` when the repository configuration produces an error finding
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- verify: visible(locator="doctor output", text="warning:")
- code: `farrier/farrier/doctor.py::report`
- detail: [repository diagnosis](concepts/doctor-diagnosis.md)
- tests: `farrier/tests/test_doctor_command.py::test_a_repo_with_no_services_block_is_warned_that_nothing_is_gated`
- tests: `farrier/tests/test_doctor_command.py::test_a_missing_agents_yml_is_the_one_error`
- tests: `farrier/tests/test_doctor_command.py::test_warnings_alone_exit_zero`

`doctor` does not resolve a library, render files, or fail merely because a repository has not
adopted a workflow gate. Its only nonzero result is an unreadable or invalid `agents.yml`.

### hooks
- usage: `farrier hooks [--repo DIR]`
- flags:
  - `--repo <dir>` — repository root whose hook manager is wired. Default: current working
    directory.
- does:
  - run: resolve the supplied repository path to an absolute path
  - run: read `<repo>/agents.yml` when it exists, otherwise use an empty configuration
  - run: choose `hooks.manager` when declared as one of `pre-commit`, `lefthook`, `husky`,
    `githooks`, or `none`
  - run: detect the repository's hook manager from marker files when `hooks.manager` is absent
  - run: reject a declared manager outside the accepted manager vocabulary
  - run: remove Farrier's fenced hook entry from every supported manager file when the manager is
    `none`
  - run: replace a legacy whole-file Farrier hook before writing a new fenced entry
  - run: write the manager-specific fenced entry that delegates to `make farrier-run-hook`
  - run: preserve user-owned lines outside Farrier's fenced region
  - run: create missing `husky` and `githooks` shell hook files with an executable preamble
  - run: ensure a newly created pre-commit configuration begins with `repos:`
  - run: set Git `core.hooksPath` to `.githooks` for the `githooks` manager
  - run: print messages for changed or removed hook-manager files
  - run: print the selected manager as `hooks wired through: <manager>`
  - run: perform hook wiring without resolving a library or rendering repository outputs
- errors:
  - print the invalid `hooks.manager` value and the accepted manager names when configuration names
    an unsupported manager
- exits:
  - return `0` after wiring completes, including when no `agents.yml` exists
  - terminate nonzero when `hooks.manager` is invalid
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- verify: persists(subject="configured repository hook-manager fence")
- verify: unchanged(subject="user-owned lines outside hook-manager fence")
- verify: persists(subject="githooks core.hooksPath")
- code: `farrier/farrier/cli.py::_run_hooks`
- detail: [hook manager wiring](concepts/hook-manager-wiring.md)
- tests: `farrier/tests/test_hook_managers.py::test_the_hooks_command_wires_a_repo_whose_packs_do_not_resolve`
- tests: `farrier/tests/test_hook_managers.py::test_the_hooks_command_falls_back_to_detection_with_no_agents_yml`
