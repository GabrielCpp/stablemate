---
type: fragment
slug: farrier-commands-init
title: 'farrier — render the agent prompt library into a repository: Commands'
---
# farrier — render the agent prompt library into a repository: Commands

- host: [farrier — render the agent prompt library into a repository](farrier.md)

## Commands

### init
- usage: `farrier init [--repo DIR] [--force]`
- flags:
  - `--repo <dir>` — repository root to write `agents.yml` into. Default: current working
    directory.
  - `--force` — replace an existing `agents.yml` instead of refusing.
- does:
  - resolve `--repo` to an absolute path
    - run: invoke(argv=["init", "--repo", "c001"], env={"HOME": "c001/home", "STABLEMATE_CONFIG": "c001/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c001/pipx-stub-bin:$PATH"})
    - verify: stdout(matches="(?m)^Wrote /")
    - fixture: empty-dir dir=c001
  - raise `SystemExit("error: <repo> is not a directory")` when the resolved path is not a
    directory
    - run: invoke(argv=["init", "--repo", "missing"])
    - verify: stderr(text="is not a directory")
    - fixture: none, because the named directory is deliberately absent
  - refuse to replace an existing `<repo>/agents.yml` unless `--force` was given, naming the
    existing path, recommending `install` and identifying `--force` as the explicit replacement
    - run: invoke(argv=["init", "--repo", "c002"], env={"HOME": "c002/home", "STABLEMATE_CONFIG": "c002/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c002/pipx-stub-bin:$PATH"})
    - verify: stderr(text="already exists")
    - fixture: configured-repo dir=c002
  - leave the existing `agents.yml` untouched after the refusal
    - run: invoke(argv=["init", "--repo", "c003"], env={"HOME": "c003/home", "STABLEMATE_CONFIG": "c003/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c003/pipx-stub-bin:$PATH"})
    - verify: unchanged(subject="c003/agents.yml")
    - fixture: configured-repo dir=c003
  - replace the existing `agents.yml` with the starter config under `--force`
    - run: invoke(argv=["init", "--repo", "c004", "--force"], env={"HOME": "c004/home", "STABLEMATE_CONFIG": "c004/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c004/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c004/agents.yml", text="packs: []")
    - fixture: configured-repo dir=c004
  - render the starter config from the module template and write it to `<repo>/agents.yml`
    - run: invoke(argv=["init", "--repo", "c005"], env={"HOME": "c005/home", "STABLEMATE_CONFIG": "c005/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c005/pipx-stub-bin:$PATH"})
    - verify: created(subject="c005/agents.yml")
    - fixture: empty-dir dir=c005
  - seed `packs: []`, so the starter installs no skill into the repo
    - run: invoke(argv=["init", "--repo", "c006"], env={"HOME": "c006/home", "STABLEMATE_CONFIG": "c006/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c006/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c006/agents.yml", text="packs: []")
    - fixture: empty-dir dir=c006
  - enable Claude in the starter config
    - run: invoke(argv=["init", "--repo", "c007"], env={"HOME": "c007/home", "STABLEMATE_CONFIG": "c007/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c007/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c007/agents.yml", text="claude: true")
    - fixture: empty-dir dir=c007
  - write no `repo:` block, placing the repo's derived name only inside a comment
    - run: invoke(argv=["init", "--repo", "c008"], env={"HOME": "c008/home", "STABLEMATE_CONFIG": "c008/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c008/pipx-stub-bin:$PATH"})
    - verify: omits(subject="agents.yml", text="\nrepo:")
    - fixture: empty-dir dir=c008
  - print `Wrote <path>`
    - run: invoke(argv=["init", "--repo", "c009"], env={"HOME": "c009/home", "STABLEMATE_CONFIG": "c009/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c009/pipx-stub-bin:$PATH"})
    - verify: stdout(text="Wrote ")
    - fixture: empty-dir dir=c009
  - print ``Next: list this repo's own packs under `packs:`, then `farrier install`.``
    - run: invoke(argv=["init", "--repo", "c010"], env={"HOME": "c010/home", "STABLEMATE_CONFIG": "c010/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c010/pipx-stub-bin:$PATH"})
    - verify: stdout(text="then `farrier install`.")
    - fixture: empty-dir dir=c010
  - on a no, with no terminal, or when the config refuses the write, print the proposed table
    with the config path instead of installing
    - run: invoke(argv=["init", "--repo", "c011"], env={"HOME": "c011/home", "STABLEMATE_CONFIG": "c011/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c011/pipx-stub-bin:$PATH"})
    - verify: stdout(text="farrier install --user")
    - fixture: empty-dir dir=c011
  - print no proposal once a user-library table exists
    - run: invoke(argv=["init", "--repo", "c012"], env={"HOME": "c012/home", "STABLEMATE_CONFIG": "c012/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c012/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stdout", text="farrier install --user")
    - fixture: user-library-home dir=c012
- exits:
  - return `0` after writing the starter config
    - run: invoke(argv=["init", "--repo", "c013"], env={"HOME": "c013/home", "STABLEMATE_CONFIG": "c013/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c013/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=0)
    - fixture: empty-dir dir=c013
  - exit `1` when the target is not a directory or already holds an `agents.yml`
    - run: invoke(argv=["init", "--repo", "c014"], env={"HOME": "c014/home", "STABLEMATE_CONFIG": "c014/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c014/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=1)
    - fixture: configured-repo dir=c014
- code: `farrier/farrier/cli.py::_run_init` @0244d6a97e3b
- code: `farrier/farrier/init.py::default_config` @989c722f5be4
- tests: `farrier/tests/test_init_command.py::test_init_writes_a_config_the_installer_can_read`
- tests: `farrier/tests/test_init_command.py::test_init_refuses_to_overwrite_an_existing_config`
- tests: `farrier/tests/test_init_command.py::test_init_proposes_a_user_library_when_none_is_configured`
- tests: `farrier/tests/test_init_command.py::test_a_yes_writes_the_user_library_and_installs_it`
- tests: `farrier/tests/test_init_command.py::test_a_no_leaves_the_home_alone_and_prints_the_proposal`
- tests: `farrier/tests/test_init_command.py::test_init_never_asks_without_a_terminal`
- tests: `farrier/tests/test_init_command.py::test_init_proposes_nothing_once_a_user_library_exists`
- tests: `farrier/tests/test_init_command.py::test_the_proposed_user_library_installs_from_the_base_library`
- tests: `farrier/tests/test_init_command.py::test_init_needs_no_library_configured`

It reads no library, fetches no base library and needs no library configured. It is the one
command that runs before a repo is configured, so it works on a machine where
`farrier config set-library` has never been run.

When the shared config holds no `[user_library.<harness>]` table and stdin is a terminal, init asks whether to install the `general` and `stablemate` packs into the home. A yes writes a `[user_library.claude]` table selecting both packs into the shared config and runs the user install. A no, a missing terminal or a refused config write prints the proposed table instead, which the checks above observe.

- writes: `<repo>/agents.yml`, and nothing else.
- produces: [`agents.yml`](formats/agents-yml-config.md) with `agents: {claude: true}` and an empty
  `packs:` list live, and `skills`/`prompts`/`scaffolds`/`exclude`/`template`/`workflow` present
  as commented examples. No `repo:` block: the repo's name is derived from the directory.

The template is a Python string constant rather than a copy of the repo's
`farrier/agents.example.yml`: the wheel packages only the `farrier` package, so the example file
is not on disk beside an installed farrier. `agents.example.yml` stays the full reference; this is
the pruned starting point, and the two are kept consistent by hand.

### config
- usage: `farrier config [--config PATH] <set-library|set-stablemate|set-base|set-worktree|show> [args]`
- flags:
  - `--config <path>` — goes **before** the action (`farrier config --config ./c.toml show`):
    the [shared config file](../workhorse/concepts/profiles-and-config.md)
    every config verb reads and writes, instead of the discovered one. It is written back to
    `$STABLEMATE_CONFIG` rather than threaded, because `read_config` and every writer resolve
    the path themselves — one assignment moves them together. It lets the question be asked of a
    config that is not this machine's home one (a CI file, the copy a container was launched with).
  - `show --profile <name>` — print one [`[profiles.<name>]`](../workhorse/concepts/profiles-and-config.md#profiles-and-config)
    table instead of the top level, flattened to one dotted line per leaf
    (`powers.high.model=haiku`). A profile **replaces** the top-level tables rather than
    layering over them, so what it prints is the whole config that run resolves from, and two
    profiles diff against each other line by line — that flattening is what `cat` cannot do, since
    a profile is three tables deep. A `key` given alongside it is looked up among those dotted keys
    (`show powers.high.model --profile cheap`). An undefined name exits with
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
  - `set-library` resolves `path` to an absolute path (`~` expansion), validates it as a
    [library directory](concepts/library-directory.md) with `is_library_dir`, persists it as
    `library_dir` in the [home config file](formats/home-config.md) via `write_library_dir`, and prints
    `library_dir=<path>`
    - run: invoke(argv=["config", "--config", "c015/c.toml", "set-library", "c015/lib"], env={"HOME": "c015/home", "STABLEMATE_CONFIG": "c015/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c015/pipx-stub-bin:$PATH"})
    - verify: stdout(text="library_dir=")
    - fixture: library-dir-with-packs dir=c015
  - `set-library` refuses a path that lacks `library/` or `packs/`
    - run: invoke(argv=["config", "--config", "c016/c.toml", "set-library", "c016/empty"], env={"HOME": "c016/home", "STABLEMATE_CONFIG": "c016/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c016/pipx-stub-bin:$PATH"})
    - verify: stderr(text="is not a usable library directory")
    - fixture: empty-dir dir=c016
  - `set-stablemate` resolves `path` to an absolute path and persists it as `stablemate_dir`
    in the [home config file](formats/home-config.md) via `write_stablemate_dir` (no validation),
    printing `stablemate_dir=<path>`
    - run: invoke(argv=["config", "--config", "c017/c.toml", "set-stablemate", "c017"], env={"HOME": "c017/home", "STABLEMATE_CONFIG": "c017/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c017/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c017/c.toml", text="stablemate_dir")
    - fixture: empty-dir dir=c017
  - `set-base` resolves `path` to an absolute path, validates it with `is_library_dir`,
    persists it as `base_dir` in the [home config file](formats/home-config.md) via `write_base_dir`, and
    prints `base_dir=<path>`
    - run: invoke(argv=["config", "--config", "c018/c.toml", "set-base", "c018/lib"], env={"HOME": "c018/home", "STABLEMATE_CONFIG": "c018/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c018/pipx-stub-bin:$PATH"})
    - verify: stdout(text="base_dir=")
    - fixture: library-dir-with-packs dir=c018
  - `set-worktree` resolves `path` to an absolute path and persists it as `worktree_dir`
    in the [home config file](formats/home-config.md) via `write_worktree_dir` (no validation),
    printing `worktree_dir=<path>`
    - run: invoke(argv=["config", "--config", "c019/c.toml", "set-worktree", "c019/not-yet-there"], env={"HOME": "c019/home", "STABLEMATE_CONFIG": "c019/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c019/pipx-stub-bin:$PATH"})
    - verify: stdout(text="worktree_dir=")
    - fixture: empty-dir dir=c019
  - any action writes `--config`, when given, into `$STABLEMATE_CONFIG` before dispatch
    - run: invoke(argv=["config", "--config", "c020/c.toml", "set-worktree", "c020/x"], env={"HOME": "c020/home", "STABLEMATE_CONFIG": "c020/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c020/pipx-stub-bin:$PATH"})
    - verify: created(subject="c020/c.toml")
    - fixture: empty-dir dir=c020
  - `show` reads the [home config file](formats/home-config.md) via `read_config`
    - run: invoke(argv=["config", "--config", "c021/c.toml", "show"], env={"HOME": "c021/home", "STABLEMATE_CONFIG": "c021/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c021/pipx-stub-bin:$PATH"})
    - verify: stdout(text="library_dir=")
    - fixture: library-config dir=c021
  - `show --profile` narrows the config with `select_profile` and flattens it to dotted
    leaves first
    - run: invoke(argv=["config", "--config", "c022/c.toml", "show", "--profile", "cheap"], env={"HOME": "c022/home", "STABLEMATE_CONFIG": "c022/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c022/pipx-stub-bin:$PATH"})
    - verify: stdout(text="powers.high.model=haiku")
    - fixture: profiles-config dir=c022
  - `show --profile` replaces the top-level tables instead of layering over them
    - run: invoke(argv=["config", "--config", "c023/c.toml", "show", "--profile", "cheap"], env={"HOME": "c023/home", "STABLEMATE_CONFIG": "c023/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c023/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stdout", text="powers.high.model=opus")
    - fixture: profiles-config dir=c023
  - `show <key>` prints the key's bare value
    - run: invoke(argv=["config", "--config", "c024/c.toml", "show", "powers.high.model", "--profile", "cheap"], env={"HOME": "c024/home", "STABLEMATE_CONFIG": "c024/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c024/pipx-stub-bin:$PATH"})
    - verify: stdout(text="haiku")
    - fixture: profiles-config dir=c024
  - `show <key>` exits with an error if the key is unset, naming the profile when one was given
    - run: invoke(argv=["config", "--config", "c025/c.toml", "show", "nonesuch"], env={"HOME": "c025/home", "STABLEMATE_CONFIG": "c025/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c025/pipx-stub-bin:$PATH"})
    - verify: stderr(text="is not set in")
    - fixture: profiles-config dir=c025
  - `show` without a key prints every entry as `key=value`
    - run: invoke(argv=["config", "--config", "c026/c.toml", "show"], env={"HOME": "c026/home", "STABLEMATE_CONFIG": "c026/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c026/pipx-stub-bin:$PATH"})
    - verify: stdout(text="=")
    - fixture: profiles-config dir=c026
  - an undefined profile name exits with `UnknownProfileError`, which lists the ones the file
    does define
    - run: invoke(argv=["config", "--config", "c027/c.toml", "show", "--profile", "nonesuch"], env={"HOME": "c027/home", "STABLEMATE_CONFIG": "c027/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c027/pipx-stub-bin:$PATH"})
    - verify: stderr(text="cheap")
    - fixture: profiles-config dir=c027
- code: `farrier/farrier/cli.py::_run_config` @0244d6a97e3b
- tests: `farrier/tests/test_config_profiles_cli.py::test_the_config_flag_reads_the_file_it_names`,
   `farrier/tests/test_config_profiles_cli.py::test_a_profile_is_shown_flattened_to_dotted_keys`,
   `farrier/tests/test_config_profiles_cli.py::test_the_profile_replaces_the_top_level_rather_than_layering_over_it`,
   `farrier/tests/test_config_profiles_cli.py::test_an_unknown_profile_exits_cleanly_and_lists_the_ones_there_are`,
   `farrier/tests/test_config_profiles_cli.py::test_set_worktree_records_a_directory_that_does_not_exist_yet`

The one command that reads and writes the [shared config file](../workhorse/concepts/profiles-and-config.md):
workhorse is a library and ships no `config` of its own, so `agents.mk` and other scripts go
through farrier for every shared setting. The nested `[power.<tier>.<backend>]` and
[`[profiles.<name>]`](../workhorse/concepts/profiles-and-config.md#profiles-and-config) tables have no writer subcommand
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
  - resolve the [library directory](concepts/library-directory.md) into the active layer stack
    - run: invoke(argv=["library", "list", "--skills"], env={"HOME": "c028/home", "STABLEMATE_CONFIG": "c028/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c028/pipx-stub-bin:$PATH"})
    - verify: stdout(text="(base)")
    - fixture: overlay-over-base dir=c028
  - raise `SystemExit` when both configuration and an installed base library are absent
    - run: invoke(argv=["library", "list"], env={"HOME": "c029/home", "STABLEMATE_CONFIG": "c029/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c029/pipx-stub-bin:$PATH"})
    - verify: stderr(text="no library available")
    - fixture: no-library-layers dir=c029
  - raise `SystemExit` when no mode is given
    - run: invoke(argv=["library"], env={"HOME": "c030/home", "STABLEMATE_CONFIG": "c030/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c030/pipx-stub-bin:$PATH"})
    - verify: stderr(text="needs a mode: list, show or check")
    - fixture: overlay-over-base dir=c030
  - `list` prints the layer stack as one `# layer: <name>` header per layer
    - run: invoke(argv=["library", "list", "--skills"], env={"HOME": "c031/home", "STABLEMATE_CONFIG": "c031/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c031/pipx-stub-bin:$PATH"})
    - verify: stdout(text="# layer: ")
    - fixture: overlay-over-base dir=c031
  - `list` prints one `## <kind> (<count>)` block for each selected kind
    - run: invoke(argv=["library", "list", "--skills"], env={"HOME": "c032/home", "STABLEMATE_CONFIG": "c032/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c032/pipx-stub-bin:$PATH"})
    - verify: stdout(matches="(?m)^## skills \\([0-9]+\\)$")
    - fixture: overlay-over-base dir=c032
  - `list` prints each item's library id, installed name and resolving layer
    - run: invoke(argv=["library", "list", "--skills"], env={"HOME": "c033/home", "STABLEMATE_CONFIG": "c033/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c033/pipx-stub-bin:$PATH"})
    - verify: stdout(text="stacks/api  api")
    - fixture: overlay-over-base dir=c033
  - `list` prints the layers each item shadows
    - run: invoke(argv=["library", "list", "--skills"], env={"HOME": "c034/home", "STABLEMATE_CONFIG": "c034/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c034/pipx-stub-bin:$PATH"})
    - verify: stdout(matches="\\(shadows [^)]+\\)")
    - fixture: overlay-over-base dir=c034
  - `list` reports one layer when base and overlay name the same directory, so a repo that
    pins its own tree as both does not report it as shadowing itself
    - run: invoke(argv=["library", "list", "--skills"], env={"HOME": "c035/home", "STABLEMATE_CONFIG": "c035/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c035/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stdout", text="(shadows")
    - fixture: one-tree-as-both dir=c035
  - `list --layer` reports what that layer **provides**, including items the other layer
    shadows — filtering on the winner would answer a different question than the one asked
    - run: invoke(argv=["library", "list", "--skills", "--layer", "base"], env={"HOME": "c036/home", "STABLEMATE_CONFIG": "c036/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c036/pipx-stub-bin:$PATH"})
    - verify: stdout(text="# layer: base-library (base)")
    - fixture: overlay-over-base dir=c036
  - `show` resolves NAME by library id, then installed name, then bare basename
    - run: invoke(argv=["library", "show", "--skill", "stacks/api"], env={"HOME": "c037/home", "STABLEMATE_CONFIG": "c037/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c037/pipx-stub-bin:$PATH"})
    - verify: stdout(text="name: api")
    - fixture: overlay-over-base dir=c037
  - `show` resolves a bare basename shared by two folders to the first of them by library id,
    because library names are unique across a library and the two folders form one item
    - run: invoke(argv=["library", "show", "--skill", "api"], env={"HOME": "c038/home", "STABLEMATE_CONFIG": "c038/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c038/pipx-stub-bin:$PATH"})
    - verify: stdout(text="name: stacks-api")
    - fixture: two-api-skills dir=c038
  - `show` refuses an unknown NAME, listing the full library-id catalog
    - run: invoke(argv=["library", "show", "--skill", "nonesuch"], env={"HOME": "c039/home", "STABLEMATE_CONFIG": "c039/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c039/pipx-stub-bin:$PATH"})
    - verify: stderr(text="The stack provides:")
    - fixture: two-api-skills dir=c039
  - `show --layer` refuses an item the named layer does not provide, naming the layer it comes from
    - run: invoke(argv=["library", "show", "--skill", "stacks/api", "--layer", "base"], env={"HOME": "c040/home", "STABLEMATE_CONFIG": "c040/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c040/pipx-stub-bin:$PATH"})
    - verify: stderr(text="does not provide skill")
    - fixture: overlay-only-skill dir=c040
  - `show` prints the selected source file verbatim, so the output pipes
    - run: invoke(argv=["library", "show", "--skill", "stacks/api"], env={"HOME": "c041/home", "STABLEMATE_CONFIG": "c041/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c041/pipx-stub-bin:$PATH"})
    - verify: stdout(text="description:")
    - fixture: overlay-over-base dir=c041
  - `check` runs `check_library` over each layer's `library/` root and prints the findings
    - run: invoke(argv=["library", "check"], env={"HOME": "c042/home", "STABLEMATE_CONFIG": "c042/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c042/pipx-stub-bin:$PATH"})
    - verify: stdout(text="# layer: ")
    - fixture: overlay-over-base dir=c042
- exits:
  - `check` returns `1` on any error, or any warning under `--strict`
    - run: invoke(argv=["library", "check"], env={"HOME": "c043/home", "STABLEMATE_CONFIG": "c043/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c043/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=1)
    - fixture: broken-skill-library dir=c043
  - `list`, `show` and a clean `check` return `0`
    - run: invoke(argv=["library", "list"], env={"HOME": "c044/home", "STABLEMATE_CONFIG": "c044/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c044/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=0)
    - fixture: overlay-over-base dir=c044
- code: `farrier/farrier/cli.py::_run_library` @0244d6a97e3b
- code: `farrier/farrier/library_view.py::format_list` @8ec27bce6b5d
- code: `farrier/farrier/library_view.py::find` @8ec27bce6b5d
- code: `farrier/farrier/library_view.py::stack` @8ec27bce6b5d
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
  - `<file>` — path to a farrier-generated `SKILL.md`, command `.md` file, or aggregated
    `AGENTS.md`/`CLAUDE.md`. Required.
- does:
  - resolve `<file>` to an absolute path
    - run: invoke(argv=["source", "c045/.claude/skills/acme-demo/SKILL.md", "--library", "c045/library-dir"], env={"HOME": "c045/home", "STABLEMATE_CONFIG": "c045/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c045/pipx-stub-bin:$PATH"})
    - verify: stdout(matches="(?m)^/")
    - fixture: generated-demo-skill dir=c045
  - `SystemExit` if `<file>` is not a file
    - run: invoke(argv=["source", "c046/missing/SKILL.md"], env={"HOME": "c046/home", "STABLEMATE_CONFIG": "c046/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c046/pipx-stub-bin:$PATH"})
    - verify: stderr(text="is not a file")
    - fixture: empty-dir dir=c046
  - read `<file>`'s YAML front matter and parse its
    [`metadata:` block](formats/generated-file-metadata.md) via `frontmatter_metadata`, extracting the
    `source` field (a library-anchored, machine-independent path stamped in by `install`'s
    generated-file provenance banner)
    - run: invoke(argv=["source", "c047/.claude/skills/acme-demo/SKILL.md", "--library", "c047/library-dir"], env={"HOME": "c047/home", "STABLEMATE_CONFIG": "c047/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c047/pipx-stub-bin:$PATH"})
    - verify: stdout(text="library/skills/demo")
    - fixture: generated-demo-skill dir=c047
  - for an `AGENTS.md` or `CLAUDE.md` with no `metadata.source`, resolve the sources through the
    `localInstructions` mapping of the nearest `agents.yml` above it, and fall back to the library
    paths its leading `generated by farrier` banner lists when no `agents.yml` is found
    - run: invoke(argv=["source", "c048/AGENTS.md", "--library", "c048/library-dir"], env={"HOME": "c048/home", "STABLEMATE_CONFIG": "c048/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c048/pipx-stub-bin:$PATH"})
    - verify: stdout(matches="(?m)demo/SKILL\\.md$")
    - fixture: aggregated-agents-md dir=c048
  - credit a `text` entry of that mapping to `agents.yml` itself and print the path of that file
    - run: invoke(argv=["source", "c049/AGENTS.md", "--library", "c049/library-dir"], env={"HOME": "c049/home", "STABLEMATE_CONFIG": "c049/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c049/pipx-stub-bin:$PATH"})
    - verify: stdout(text="agents.yml")
    - fixture: text-instructions-md dir=c049
  - `SystemExit` if the file has neither `source` front matter nor a farrier banner (it is not a
    farrier-generated file)
    - run: invoke(argv=["source", "c050/NOTES.md", "--library", "c050/library-dir"], env={"HOME": "c050/home", "STABLEMATE_CONFIG": "c050/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c050/pipx-stub-bin:$PATH"})
    - verify: stderr(text="it is not a farrier-generated file")
    - fixture: plain-notes-file dir=c050
  - resolve the [library directory](concepts/library-directory.md) the same way `install`
    does (`--library` > `$FARRIER_LIBRARY_DIR` > home config), then search each layer for every
    source and resolve it to an absolute path
    - run: invoke(argv=["source", "c051/.claude/skills/acme-demo/SKILL.md", "--library", "c051/library-dir"], env={"HOME": "c051/home", "STABLEMATE_CONFIG": "c051/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c051/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stderr", text="set-library")
    - fixture: generated-demo-skill dir=c051
  - `SystemExit` if a source is in no layer because the library moved or renamed it since the file
    was generated, naming the layers searched
    - run: invoke(argv=["source", "c052/.claude/skills/acme-demo/SKILL.md", "--library", "c052/library-dir"], env={"HOME": "c052/home", "STABLEMATE_CONFIG": "c052/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c052/pipx-stub-bin:$PATH"})
    - verify: stderr(text="does not exist in any library layer")
    - fixture: moved-source-skill dir=c052
  - print the resolved absolute path of each source, one per line
    - run: invoke(argv=["source", "c053/.claude/skills/acme-demo/SKILL.md", "--library", "c053/library-dir"], env={"HOME": "c053/home", "STABLEMATE_CONFIG": "c053/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c053/pipx-stub-bin:$PATH"})
    - verify: stdout(text="library/skills/demo/SKILL.md")
    - fixture: generated-demo-skill dir=c053
  - print `note: resolved from layer <name>` on stderr when more than one library layer is active
    - run: invoke(argv=["source", "c054/.claude/skills/acme-demo/SKILL.md", "--library", "c054/library-dir"], env={"HOME": "c054/home", "STABLEMATE_CONFIG": "c054/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c054/pipx-stub-bin:$PATH"})
    - verify: stderr(text="note: resolved from layer")
    - fixture: generated-demo-skill dir=c054
- exits:
  - return `0` after printing every source path
    - run: invoke(argv=["source", "c055/.claude/skills/acme-demo/SKILL.md", "--library", "c055/library-dir"], env={"HOME": "c055/home", "STABLEMATE_CONFIG": "c055/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c055/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=0)
    - fixture: generated-demo-skill dir=c055
- code: `farrier/farrier/cli.py::_run_source` @0244d6a97e3b
- code: `farrier/farrier/cli.py::mapped_instruction_sources` @0244d6a97e3b
- code: `farrier/farrier/frontmatter.py::frontmatter_metadata` @9cdb7d1662b8
- code: `farrier/farrier/frontmatter.py::banner_sources` @9cdb7d1662b8
- tests: `farrier/tests/test_source_command.py::test_source_resolves_to_library_file`
- tests: `farrier/tests/test_source_command.py::test_frontmatter_metadata_reads_nested_block`
- tests: `farrier/tests/test_source_command.py::test_frontmatter_metadata_empty_without_block`

Lets an agent go from a generated adapter under `.claude/`/`.agents/`/`.github/` back to its
editable source of truth in the library, using only the generated file's front matter, its
aggregation mapping or its banner. `frontmatter_metadata` is declared in the frontmatter parser;
`install.py` only re-exports it as a compatibility facade.

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
  - resolve the [library directory](concepts/library-directory.md), then load every scaffold
    definition from its `scaffolds/*.yml`/`*.yaml` files (`load_scaffold_defs`)
    - run: invoke(argv=["scaffold", "--list", "--library", "c056/scaffold-library", "--repo", "c056"], env={"HOME": "c056/home", "STABLEMATE_CONFIG": "c056/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c056/pipx-stub-bin:$PATH"})
    - verify: stdout(matches="(?m)^service-gitignore")
    - fixture: scaffold-library dir=c056
  - interpret each scaffold file as ids mapped to `{description?, params?, tree}` definitions
    - run: invoke(argv=["scaffold", "--list", "--library", "c057/scaffold-library", "--repo", "c057"], env={"HOME": "c057/home", "STABLEMATE_CONFIG": "c057/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c057/pipx-stub-bin:$PATH"})
    - verify: stdout(text="Ignore rules for a service")
    - fixture: described-scaffold-library dir=c057
  - raise `SystemExit` when two files in one layer define the same scaffold id
    - run: invoke(argv=["scaffold", "--list", "--library", "c058/scaffold-library", "--repo", "c058"], env={"HOME": "c058/home", "STABLEMATE_CONFIG": "c058/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c058/pipx-stub-bin:$PATH"})
    - verify: stderr(text="Duplicate scaffold id")
    - fixture: duplicate-scaffold-library dir=c058
  - raise `SystemExit` when a scaffold definition is not a mapping with a `tree:` mapping
    - run: invoke(argv=["scaffold", "--list", "--library", "c059/scaffold-library", "--repo", "c059"], env={"HOME": "c059/home", "STABLEMATE_CONFIG": "c059/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c059/pipx-stub-bin:$PATH"})
    - verify: stderr(text="must be a mapping with a `tree:`")
    - fixture: treeless-scaffold-library dir=c059
  - with `<repo>/agents.yml`, compute the repo's catalog (`available_scaffold_ids`) as the
    union of its `scaffolds:` list plus every selected pack's `scaffolds:` list
    - run: invoke(argv=["scaffold", "--list", "--library", "c060/scaffold-library", "--repo", "c060"], env={"HOME": "c060/home", "STABLEMATE_CONFIG": "c060/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c060/pipx-stub-bin:$PATH"})
    - verify: stdout(text="--param dir=...  (default: api)")
    - fixture: scaffold-library dir=c060
  - reject non-string catalog entries, including the legacy `{source-prefix: dest}` mapping
    form, with a migration hint from `parse_scaffold_ids`
    - run: invoke(argv=["scaffold", "--list", "--library", "c061/scaffold-library", "--repo", "c061"], env={"HOME": "c061/home", "STABLEMATE_CONFIG": "c061/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c061/pipx-stub-bin:$PATH"})
    - verify: stderr(text="scaffolds entries must be scaffold ids")
    - fixture: legacy-scaffolds-repo dir=c061
  - with no `agents.yml`, expose every library scaffold id to bootstrap a fresh repo
    - run: invoke(argv=["scaffold", "--list", "--library", "c062/scaffold-library", "--repo", "c062"], env={"HOME": "c062/home", "STABLEMATE_CONFIG": "c062/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c062/pipx-stub-bin:$PATH"})
    - verify: stdout(text="service-gitignore")
    - fixture: scaffold-library-no-agents dir=c062
  - raise `SystemExit` for an `<id>` absent from the library, listing the defined ids
    - run: invoke(argv=["scaffold", "nonesuch", "--library", "c063/scaffold-library", "--repo", "c063"], env={"HOME": "c063/home", "STABLEMATE_CONFIG": "c063/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c063/pipx-stub-bin:$PATH"})
    - verify: stderr(text="Library defines: service-gitignore")
    - fixture: scaffold-library dir=c063
  - raise `SystemExit` for an `<id>` absent from the repo's catalog, pointing at the
    `agents.yml` `scaffolds:` list
    - run: invoke(argv=["scaffold", "service-gitignore", "--library", "c064/scaffold-library", "--repo", "c064"], env={"HOME": "c064/home", "STABLEMATE_CONFIG": "c064/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c064/pipx-stub-bin:$PATH"})
    - verify: stderr(text="is not enabled for this repo")
    - fixture: scaffold-library-unlisted dir=c064
  - resolve params (`resolve_scaffold_params`): declared defaults overlaid with `--param`
    values, plus built-ins `repo_name` (kebab-cased `repo.name`, else the `--repo` dirname) and `repo_title`
    (title-cased words) unless shadowed
    - run: invoke(argv=["scaffold", "service-gitignore", "--param", "dir=backend", "--library", "c065/scaffold-library", "--repo", "c065"], env={"HOME": "c065/home", "STABLEMATE_CONFIG": "c065/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c065/pipx-stub-bin:$PATH"})
    - verify: created(subject="c065/backend/.gitignore")
    - fixture: scaffold-library dir=c065
  - flatten string values in the definition's `tree:` into inline file content
    - run: invoke(argv=["scaffold", "service-gitignore", "--library", "c066/scaffold-library", "--repo", "c066"], env={"HOME": "c066/home", "STABLEMATE_CONFIG": "c066/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c066/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c066/api/.gitignore", text="node_modules")
    - fixture: scaffold-library dir=c066
  - recursively flatten mapping values that are nested sub-trees
    - run: invoke(argv=["scaffold", "service-gitignore", "--library", "c067/scaffold-library", "--repo", "c067"], env={"HOME": "c067/home", "STABLEMATE_CONFIG": "c067/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c067/pipx-stub-bin:$PATH"})
    - verify: created(subject="c067/api/src/main.txt")
    - fixture: nested-scaffold-library dir=c067
  - create a null tree value or empty mapping as an empty directory
    - run: invoke(argv=["scaffold", "logs-dir", "--library", "c068/scaffold-library", "--repo", "c068"], env={"HOME": "c068/home", "STABLEMATE_CONFIG": "c068/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c068/pipx-stub-bin:$PATH"})
    - verify: stdout(text="logs/")
    - fixture: scaffold-library-empty-dir dir=c068
  - report an empty directory as `created: <rel>/` or `exists (kept): <rel>/`
    - run: invoke(argv=["scaffold", "logs-dir", "--library", "c069/scaffold-library", "--repo", "c069"], env={"HOME": "c069/home", "STABLEMATE_CONFIG": "c069/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c069/pipx-stub-bin:$PATH"})
    - verify: stdout(text="created: logs/")
    - fixture: scaffold-library-empty-dir dir=c069
  - substitute `$param` placeholders strictly in each scaffold path
    - run: invoke(argv=["scaffold", "service-gitignore", "--library", "c070/scaffold-library", "--repo", "c070"], env={"HOME": "c070/home", "STABLEMATE_CONFIG": "c070/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c070/pipx-stub-bin:$PATH"})
    - verify: stdout(text="created: api/.gitignore")
    - fixture: scaffold-library dir=c070
  - raise `SystemExit` when a path contains an unknown parameter or escapes the repo
    - run: invoke(argv=["scaffold", "bad-path", "--library", "c071/scaffold-library", "--repo", "c071"], env={"HOME": "c071/home", "STABLEMATE_CONFIG": "c071/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c071/pipx-stub-bin:$PATH"})
    - verify: stderr(text="cannot resolve path")
    - fixture: scaffold-library-bad-path dir=c071
  - substitute parameters leniently (`safe_substitute`) in inline file content
    - run: invoke(argv=["scaffold", "service-gitignore", "--library", "c072/scaffold-library", "--repo", "c072"], env={"HOME": "c072/home", "STABLEMATE_CONFIG": "c072/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c072/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c072/api/.gitignore", text="# api")
    - fixture: param-content-scaffold-library dir=c072
  - write each file absent from the target repo, reporting `created: <rel>`
    - run: invoke(argv=["scaffold", "service-gitignore", "--library", "c073/scaffold-library", "--repo", "c073"], env={"HOME": "c073/home", "STABLEMATE_CONFIG": "c073/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c073/pipx-stub-bin:$PATH"})
    - verify: created(subject="c073/api/.gitignore")
    - fixture: scaffold-library dir=c073
  - preserve each existing target file, reporting `exists (kept): <rel>`
    - run: invoke(argv=["scaffold", "service-gitignore", "--library", "c074/scaffold-library", "--repo", "c074"], env={"HOME": "c074/home", "STABLEMATE_CONFIG": "c074/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c074/pipx-stub-bin:$PATH"})
    - verify: unchanged(subject="c074/api/.gitignore")
    - fixture: scaffold-library-existing dir=c074
  - make every re-run a no-op for existing files
    - run: invoke(argv=["scaffold", "service-gitignore", "--library", "c075/scaffold-library", "--repo", "c075"], env={"HOME": "c075/home", "STABLEMATE_CONFIG": "c075/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c075/pipx-stub-bin:$PATH"})
    - verify: stdout(text="0 file(s) created")
    - fixture: scaffold-library-existing dir=c075
  - print the number of files created by this invocation
    - run: invoke(argv=["scaffold", "service-gitignore", "--library", "c076/scaffold-library", "--repo", "c076"], env={"HOME": "c076/home", "STABLEMATE_CONFIG": "c076/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c076/pipx-stub-bin:$PATH"})
    - verify: stdout(text="1 file(s) created")
    - fixture: scaffold-library dir=c076
- exits:
  - return `0` after scaffolding completes
    - run: invoke(argv=["scaffold", "service-gitignore", "--library", "c077/scaffold-library", "--repo", "c077"], env={"HOME": "c077/home", "STABLEMATE_CONFIG": "c077/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c077/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=0)
    - fixture: scaffold-library dir=c077
  - return a nonzero status when the scaffold id is unknown
    - run: invoke(argv=["scaffold", "nonesuch", "--library", "c078/scaffold-library", "--repo", "c078"], env={"HOME": "c078/home", "STABLEMATE_CONFIG": "c078/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c078/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=1)
    - fixture: scaffold-library dir=c078
- code: `farrier/farrier/cli.py::_run_scaffold` @0244d6a97e3b
- tests: `farrier/tests/test_scaffold_command.py::test_scaffold_writes_tree_with_defaults`

Lets an agent stand up a new repo or service folder from the library's parameterized scaffold
definitions (per-stack `.gitignore` seeds, the standard `docs/` hierarchy) instead of hand-writing
boilerplate — placement folders are `--param` values, never baked into the library.

A `{url: ...}` scaffold file value is downloaded at write time with a 30-second timeout, and a failed download ends the run with `SystemExit`. Both need the network, so no check backs them. Every scaffolded file is a seed that the repo owns after its first write.

### version
- usage: `farrier version`
- does: print the installed `farrier` package's version (`importlib.metadata.version("farrier")`)
- run: invoke(argv=["version"])
- verify: stdout(matches="^[0-9]+\\.[0-9]+\\.[0-9]+")
- fixture: none, because the version comes from the installed package metadata
- code: `farrier/farrier/cli.py::main` @0244d6a97e3b
