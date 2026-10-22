---
type: fragment
slug: farrier-commands-install
title: 'farrier — render the agent prompt library into a repository: install'
---
# farrier — render the agent prompt library into a repository: install

- host: [farrier — render the agent prompt library into a repository](farrier.md)

## Commands

### install
- usage: `farrier install [--repo DIR] [--config PATH] [--check] [--library DIR]` (also the
  default command: `farrier [--repo DIR] [--config PATH] [--check] [--library DIR]` when the first
  argument isn't a recognized subcommand)
- run: invoke(argv=["install", "--repo", ".", "--library", "lib"])
- flags:
  - `--repo <dir>` — repository root to render generated files into. Default: current working
    directory.
  - `--config <path>` — path to the repo's [`agents.yml`](formats/agents-yml-config.md) pack/skill
    selection file. Default: `<repo>/agents.yml`.
  - `--check` — verify the repo's generated files are current without writing anything; exits `1`
    and prints which files would be rewritten if any are stale or missing, `0` otherwise.
  - `--skip-unresolvable` — with `--check`: pass, with a note, when the configured library cannot be
    resolved. It is for the git hook, which must not block a contributor who has no access to a
    private overlay layer this repo's config selects from.
  - `--library <dir>` — the library directory (the `agents/` tree). Overrides
    `$FARRIER_LIBRARY_DIR` and the home config's `library_dir` for this invocation.
- verify: unchanged(subject="repository after an install --check run")
- does:
  - resolve the [library directory](concepts/library-directory.md) (`--library` >
    `$FARRIER_LIBRARY_DIR` > home config) and point the module's library-content globals at it
    - run: invoke(argv=["install", "--repo", "c079", "--library", "c079/lib"], env={"HOME": "c079/home", "STABLEMATE_CONFIG": "c079/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c079/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stderr", text="set-library")
    - fixture: demo-skill-repo dir=c079
  - print one `info:` line per library source a higher layer replaces by name, unless `--check`
    is given
    - run: invoke(argv=["install", "--repo", "c080", "--library", "c080/lib"], env={"HOME": "c080/home", "STABLEMATE_CONFIG": "c080/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c080/pipx-stub-bin:$PATH"})
    - verify: stdout(text="overrides")
    - fixture: overlay-install-repo dir=c080
  - resolve `--repo` to an absolute path used as the generated-output root
    - run: invoke(argv=["install", "--repo", "c081", "--library", "c081/lib"], env={"HOME": "c081/home", "STABLEMATE_CONFIG": "c081/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c081/pipx-stub-bin:$PATH"})
    - verify: stdout(matches="(?m)into /.+$")
    - fixture: demo-skill-repo dir=c081
  - resolve the config path to `--config` if given, else `<repo>/agents.yml`
    - run: invoke(argv=["install", "--repo", "c082", "--config", "c082/other.yml", "--library", "c082/lib"], env={"HOME": "c082/home", "STABLEMATE_CONFIG": "c082/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c082/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stderr", text="Missing config:")
    - fixture: other-config-repo dir=c082
  - read [`agents.yml`](formats/agents-yml-config.md) via `read_yaml`
    - run: invoke(argv=["install", "--repo", "c083", "--library", "c083/lib"], env={"HOME": "c083/home", "STABLEMATE_CONFIG": "c083/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c083/pipx-stub-bin:$PATH"})
    - verify: created(subject="c083/.agents/agents-context.claude.json")
    - fixture: demo-skill-repo dir=c083
  - exit with `Missing config: <path>` and a hint to run `farrier init` when the default
    `<repo>/agents.yml` does not exist
    - run: invoke(argv=["install", "--repo", "c084", "--library", "c084/lib"], env={"HOME": "c084/home", "STABLEMATE_CONFIG": "c084/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c084/pipx-stub-bin:$PATH"})
    - verify: stderr(text="Missing config:")
    - fixture: library-dir-with-packs dir=c084
  - exit with `Config must be a YAML mapping: <path>` when the parsed value is not a mapping
    - run: invoke(argv=["install", "--repo", "c085", "--library", "c085/lib"], env={"HOME": "c085/home", "STABLEMATE_CONFIG": "c085/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c085/pipx-stub-bin:$PATH"})
    - verify: stderr(text="Config must be a YAML mapping")
    - fixture: list-agents-yml dir=c085
  - derive the install prefix from the kebab-cased `repo.name` in `agents.yml`, else from the
    repo dirname (`naming.repo_prefix`)
    - run: invoke(argv=["install", "--repo", "c086", "--library", "c086/lib"], env={"HOME": "c086/home", "STABLEMATE_CONFIG": "c086/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c086/pipx-stub-bin:$PATH"})
    - verify: created(subject="c086/.claude/skills/acme-demo/SKILL.md")
    - fixture: demo-skill-repo dir=c086
  - validate that `agents:` selects at least one of `codex`/`claude`/`copilot`
    (`normalize_agents`), else raise `SystemExit("No agents selected in config")`
    - run: invoke(argv=["install", "--repo", "c087", "--library", "c087/lib"], env={"HOME": "c087/home", "STABLEMATE_CONFIG": "c087/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c087/pipx-stub-bin:$PATH"})
    - verify: stderr(text="No agents selected in config")
    - fixture: no-agents-repo dir=c087
  - resolve the [`agents.yml`](formats/agents-yml-config.md) selection (packs ∪ top-level
    `skills`/`prompts`/`roots`, minus `exclude`) against the library's skill/prompt sources. The
    `scaffolds:` lists are collected but consumed only by the [`scaffold`](farrier-commands-init.md#scaffold) command, so
    install renders no scaffold files
    - run: invoke(argv=["install", "--repo", "c088", "--library", "c088/lib"], env={"HOME": "c088/home", "STABLEMATE_CONFIG": "c088/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c088/pipx-stub-bin:$PATH"})
    - verify: absent(subject="c088/.claude/skills/acme-other/SKILL.md")
    - fixture: excluded-skill-repo dir=c088
  - raise `SystemExit` with `unknown pack in agents.yml` when the config names a pack, skill or
    prompt that no library layer provides, listing the layers searched
    - run: invoke(argv=["install", "--repo", "c089", "--library", "c089/lib"], env={"HOME": "c089/home", "STABLEMATE_CONFIG": "c089/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c089/pipx-stub-bin:$PATH"})
    - verify: stderr(text="unknown pack in agents.yml")
    - fixture: unmatched-pack-repo dir=c089
  - render nothing about skills and print nothing about them when the config selects nothing
    - run: invoke(argv=["install", "--repo", "c090", "--library", "c090/lib"], env={"HOME": "c090/home", "STABLEMATE_CONFIG": "c090/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c090/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stdout", text="skill")
    - fixture: bare-agents-repo dir=c090
  - render every enabled agent's selected skill files through a
    [`Renderer`](concepts/renderer.md)
    - run: invoke(argv=["install", "--repo", "c091", "--library", "c091/lib"], env={"HOME": "c091/home", "STABLEMATE_CONFIG": "c091/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c091/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c091/.claude/skills/acme-demo/SKILL.md", text="name: acme-demo")
    - fixture: demo-skill-repo dir=c091
  - render every enabled agent's selected command files through the `Renderer`
    - run: invoke(argv=["install", "--repo", "c092", "--library", "c092/lib"], env={"HOME": "c092/home", "STABLEMATE_CONFIG": "c092/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c092/pipx-stub-bin:$PATH"})
    - verify: created(subject="c092/.claude/commands/acme-grill.md")
    - fixture: prompt-repo dir=c092
  - render the `roots`-driven Copilot instructions through the `Renderer`
    - run: invoke(argv=["install", "--repo", "c093", "--library", "c093/lib"], env={"HOME": "c093/home", "STABLEMATE_CONFIG": "c093/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c093/pipx-stub-bin:$PATH"})
    - verify: created(subject="c093/.github/copilot-instructions.md")
    - fixture: roots-repo dir=c093
  - render `.agents/agents.mk` for every repository
    - run: invoke(argv=["install", "--repo", "c094", "--library", "c094/lib"], env={"HOME": "c094/home", "STABLEMATE_CONFIG": "c094/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c094/pipx-stub-bin:$PATH"})
    - verify: created(subject="c094/.agents/agents.mk")
    - fixture: demo-skill-repo dir=c094
  - render `.agents/agents-context*.json` for every repository
    - run: invoke(argv=["install", "--repo", "c095", "--library", "c095/lib"], env={"HOME": "c095/home", "STABLEMATE_CONFIG": "c095/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c095/pipx-stub-bin:$PATH"})
    - verify: created(subject="c095/.agents/agents-context.json")
    - fixture: demo-skill-repo dir=c095
  - render a thin root `Makefile` only when the repository has none
    - run: invoke(argv=["install", "--repo", "c096", "--library", "c096/lib"], env={"HOME": "c096/home", "STABLEMATE_CONFIG": "c096/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c096/pipx-stub-bin:$PATH"})
    - verify: created(subject="c096/Makefile")
    - fixture: demo-skill-repo dir=c096
  - render each [`localInstructions`](formats/agents-yml-config.md#localinstructions) entry into its
    target directories' `AGENTS.md` as part of the full `{output path: content}` map
    (`render_expected`) that `--check` or install acts on
    - run: invoke(argv=["install", "--repo", "c097", "--library", "c097/lib"], env={"HOME": "c097/home", "STABLEMATE_CONFIG": "c097/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c097/pipx-stub-bin:$PATH"})
    - verify: created(subject="c097/api/AGENTS.md")
    - fixture: local-instructions-repo dir=c097
  - render a `CLAUDE.md` pointer for each local-instructions target whose entry sets
    `claudeMd: true`
    - run: invoke(argv=["install", "--repo", "c098", "--library", "c098/lib"], env={"HOME": "c098/home", "STABLEMATE_CONFIG": "c098/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c098/pipx-stub-bin:$PATH"})
    - verify: created(subject="c098/api/CLAUDE.md")
    - fixture: local-instructions-claude-repo dir=c098
  - raise `SystemExit` pointing at `farrier scaffold` when a local-instructions target
    directory does not already exist
    - run: invoke(argv=["install", "--repo", "c099", "--library", "c099/lib"], env={"HOME": "c099/home", "STABLEMATE_CONFIG": "c099/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c099/pipx-stub-bin:$PATH"})
    - verify: stderr(text="farrier scaffold")
    - fixture: missing-target-repo dir=c099
  - with `--check`, record `missing: <repo-relative path>` for an expected output absent from disk
    - run: invoke(argv=["install", "--check", "--repo", "c100", "--library", "c100/lib"], env={"HOME": "c100/home", "STABLEMATE_CONFIG": "c100/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c100/pipx-stub-bin:$PATH"})
    - verify: stdout(text="missing: .claude/skills/acme-demo/SKILL.md")
    - fixture: demo-skill-repo dir=c100
  - with `--check`, record `changed: <repo-relative path>` when an expected output's on-disk text
    differs from the expected content (both sides normalized to a single trailing newline before
    comparing)
    - run: invoke(argv=["install", "--check", "--repo", "c101", "--library", "c101/lib"], env={"HOME": "c101/home", "STABLEMATE_CONFIG": "c101/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c101/pipx-stub-bin:$PATH"})
    - verify: stdout(text="changed: .claude/skills/acme-demo/SKILL.md")
    - fixture: edited-install-repo dir=c101
  - with `--check`, scan `MANAGED_DIRS` for [generated](#ownership) files absent from the expected
    output map, recording each as `extra: <repo-relative path>`
    - run: invoke(argv=["install", "--check", "--repo", "c102", "--library", "c102/lib"], env={"HOME": "c102/home", "STABLEMATE_CONFIG": "c102/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c102/pipx-stub-bin:$PATH"})
    - verify: stdout(text="extra: .claude/skills/old/SKILL.md")
    - fixture: stale-skill-repo dir=c102
  - with `--check`, leave an untagged file in a managed directory alone instead of reporting it as
    `extra`, because it is somebody's own file and an install cannot fix it
    - run: invoke(argv=["install", "--check", "--repo", "c103", "--library", "c103/lib"], env={"HOME": "c103/home", "STABLEMATE_CONFIG": "c103/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c103/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stdout", text="extra: .claude/skills/mine/SKILL.md")
    - fixture: own-skill-repo dir=c103
  - with `--check`, omit `.agents/workflows` from the scan because Farrier no longer emits its
    legacy workflow YAML tree, so a reported leftover could not be fixed by re-rendering
    - run: invoke(argv=["install", "--check", "--repo", "c104", "--library", "c104/lib"], env={"HOME": "c104/home", "STABLEMATE_CONFIG": "c104/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c104/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stdout", text="extra: .agents/workflows/")
    - fixture: legacy-workflows-repo dir=c104
  - with `--check`, omit `.agents/local.compose.yaml` from the scan because Farrier no longer
    emits the legacy per-workflow compose override
    - run: invoke(argv=["install", "--check", "--repo", "c105", "--library", "c105/lib"], env={"HOME": "c105/home", "STABLEMATE_CONFIG": "c105/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c105/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stdout", text="extra: .agents/local.compose.yaml")
    - fixture: legacy-compose-repo dir=c105
  - with `--check`, keep `.github/instructions` in `MANAGED_DIRS` so a later install reports the
    per-skill `<name>.instructions.md` copies tagged by an older install
    - run: invoke(argv=["install", "--check", "--repo", "c106", "--library", "c106/lib"], env={"HOME": "c106/home", "STABLEMATE_CONFIG": "c106/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c106/pipx-stub-bin:$PATH"})
    - verify: stdout(text="extra: .github/instructions/old.instructions.md")
    - fixture: legacy-instructions-repo dir=c106
  - with `--check`, also record as `extra` every existing Farrier-owned fixed path absent from
    the expected map: `.github/copilot-instructions.md`, `.agents/agents.mk`,
    `.agents/lefthook.farrier.yml`, `.agents/agents-context.json`
    - run: invoke(argv=["install", "--check", "--repo", "c107", "--library", "c107/lib"], env={"HOME": "c107/home", "STABLEMATE_CONFIG": "c107/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c107/pipx-stub-bin:$PATH"})
    - verify: stdout(text="extra: .agents/lefthook.farrier.yml")
    - fixture: lefthook-leftover-repo dir=c107
  - with `--check`, print the recorded `missing`, `changed`, `extra` and `hooks` entries in that
    order, each with an explanation of how to resolve it
    - run: invoke(argv=["install", "--check", "--repo", "c108", "--library", "c108/lib"], env={"HOME": "c108/home", "STABLEMATE_CONFIG": "c108/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c108/pipx-stub-bin:$PATH"})
    - verify: stdout(matches="(?s)missing: .*changed: .*extra: ")
    - fixture: mixed-drift-repo dir=c108
  - with `--check`, close the drift report with a footer
    - run: invoke(argv=["install", "--check", "--repo", "c109", "--library", "c109/lib"], env={"HOME": "c109/home", "STABLEMATE_CONFIG": "c109/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c109/pipx-stub-bin:$PATH"})
    - verify: stdout(text="The comparison is against the working tree")
    - fixture: edited-install-repo dir=c109
  - with `--check`, produce no output when no drift entries were recorded
    - run: invoke(argv=["install", "--check", "--repo", "c110", "--library", "c110/lib"], env={"HOME": "c110/home", "STABLEMATE_CONFIG": "c110/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c110/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stdout", text="missing:")
    - fixture: current-install-repo dir=c110
  - with `--check` and `--skip-unresolvable`, print `Skipped the generated-file check: <reason>`
    and return `0` when the configured library cannot be resolved
    - run: invoke(argv=["install", "--check", "--skip-unresolvable", "--repo", "c111", "--library", "c111/lib"], env={"HOME": "c111/home", "STABLEMATE_CONFIG": "c111/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c111/pipx-stub-bin:$PATH"})
    - verify: stdout(text="Skipped the generated-file check:")
    - fixture: unmatched-pack-repo dir=c111
  - refuse the install through `refuse_conflicts` when an expected output path is held by a file
    Farrier did not generate, according to the [ownership](#ownership) contract
    - run: invoke(argv=["install", "--repo", "c112", "--library", "c112/lib"], env={"HOME": "c112/home", "STABLEMATE_CONFIG": "c112/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c112/pipx-stub-bin:$PATH"})
    - verify: stderr(text="farrier will not overwrite files it did not generate")
    - fixture: held-output-repo dir=c112
  - name every unowned output conflict in the refusal
    - run: invoke(argv=["install", "--repo", "c113", "--library", "c113/lib"], env={"HOME": "c113/home", "STABLEMATE_CONFIG": "c113/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c113/pipx-stub-bin:$PATH"})
    - verify: stderr(text="2 path(s) it renders are held by untagged files")
    - fixture: held-output-repo dir=c113
  - write nothing after detecting an unowned output conflict
    - run: invoke(argv=["install", "--repo", "c114", "--library", "c114/lib"], env={"HOME": "c114/home", "STABLEMATE_CONFIG": "c114/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c114/pipx-stub-bin:$PATH"})
    - verify: unchanged(subject="c114/.claude/skills/acme-demo/SKILL.md")
    - fixture: held-output-repo dir=c114
  - remove only Farrier-owned output files under the managed directories and files
    - run: invoke(argv=["install", "--repo", "c115", "--library", "c115/lib"], env={"HOME": "c115/home", "STABLEMATE_CONFIG": "c115/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c115/pipx-stub-bin:$PATH"})
    - verify: removed(subject="c115/.claude/skills/old/SKILL.md")
    - fixture: stale-skill-repo dir=c115
  - remove empty directories left by Farrier-owned output deletion
    - run: invoke(argv=["install", "--repo", "c116", "--library", "c116/lib"], env={"HOME": "c116/home", "STABLEMATE_CONFIG": "c116/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c116/pipx-stub-bin:$PATH"})
    - verify: absent(subject="c116/.claude/skills/old")
    - fixture: stale-skill-repo dir=c116
  - delete the convention-owned legacy `.agents/local.compose.yaml` when it is present, even
    though current rendering no longer produces it
    - run: invoke(argv=["install", "--repo", "c117", "--library", "c117/lib"], env={"HOME": "c117/home", "STABLEMATE_CONFIG": "c117/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c117/pipx-stub-bin:$PATH"})
    - verify: removed(subject="c117/.agents/local.compose.yaml")
    - fixture: legacy-compose-repo dir=c117
  - leave untagged neighboring files in place during removal
    - run: invoke(argv=["install", "--repo", "c118", "--library", "c118/lib"], env={"HOME": "c118/home", "STABLEMATE_CONFIG": "c118/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c118/pipx-stub-bin:$PATH"})
    - verify: unchanged(subject="c118/.claude/skills/mine/SKILL.md")
    - fixture: own-skill-repo dir=c118
  - when `.agents/agents.mk` is among the outputs, refresh the managed `.agents/` ignore rules
    and print `Updated .agents .gitignore rules`
    - run: invoke(argv=["install", "--repo", "c119", "--library", "c119/lib"], env={"HOME": "c119/home", "STABLEMATE_CONFIG": "c119/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c119/pipx-stub-bin:$PATH"})
    - verify: stdout(text="Updated .agents .gitignore rules")
    - fixture: demo-skill-repo dir=c119
  - when `.agents/agents.mk` is among the outputs and a root `Makefile` exists, append the
    launcher include without replacing the existing file
    - run: invoke(argv=["install", "--repo", "c120", "--library", "c120/lib"], env={"HOME": "c120/home", "STABLEMATE_CONFIG": "c120/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c120/pipx-stub-bin:$PATH"})
    - verify: stdout(text="Added agent launcher include to root Makefile")
    - fixture: makefile-repo dir=c120
  - when a hook manager is supplied, splice Farrier's fenced hook entry after all generated
    files have been written
    - run: invoke(argv=["install", "--repo", "c121", "--library", "c121/lib"], env={"HOME": "c121/home", "STABLEMATE_CONFIG": "c121/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c121/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c121/.pre-commit-config.yaml", text="make farrier-run-hook")
    - fixture: precommit-install-repo dir=c121
  - print `Installed <N> generated files into <repo>`
    - run: invoke(argv=["install", "--repo", "c122", "--library", "c122/lib"], env={"HOME": "c122/home", "STABLEMATE_CONFIG": "c122/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c122/pipx-stub-bin:$PATH"})
    - verify: stdout(text="generated files into")
    - fixture: demo-skill-repo dir=c122
- exits:
  - `--check` returns `1` when any `missing`/`changed`/`extra` entries were recorded
    - run: invoke(argv=["install", "--check", "--repo", "c123", "--library", "c123/lib"], env={"HOME": "c123/home", "STABLEMATE_CONFIG": "c123/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c123/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=1)
    - fixture: demo-skill-repo dir=c123
  - `--check` returns `0` when no drift entries were recorded
    - run: invoke(argv=["install", "--check", "--repo", "c124", "--library", "c124/lib"], env={"HOME": "c124/home", "STABLEMATE_CONFIG": "c124/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c124/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=0)
    - fixture: current-install-repo dir=c124
- code: `farrier/farrier/outputs.py::install_outputs` @0b63626747f4
- code: `farrier/farrier/cli.py::_run_install` @0244d6a97e3b
- tests: `farrier/tests/test_tagged_deletion.py::test_an_untagged_file_at_an_output_path_aborts_the_whole_install`
- tests: `farrier/tests/test_tagged_deletion.py::test_a_deselected_skill_is_still_removed`
- tests: `farrier/tests/test_qa_evidence_ignore.py::test_the_install_follows_the_skill_that_ships_the_gate`
- tests: `farrier/tests/test_makefile_include.py::test_appends_include_block_and_preserves_existing`
- tests: `farrier/tests/test_hook_managers.py::test_every_manager_gets_the_command_and_keeps_the_users_lines`
- detail: [hook manager wiring](concepts/hook-manager-wiring.md)

A scratch-directory run cannot observe several parts of an install, so no check backs them. Before anything looks for the library, install calls `ensure_base_library_dir(ref=farrier-v<version> or main, refresh=not --check)`. That call fetches an absent [base library](concepts/library-directory.md#fetching-and-updating-the-base) into `~/.cache/stablemate`. It updates a cached one to this farrier's release tag, or to `main` when farrier was installed from a checkout or a URL. It does neither when `$STABLEMATE_BASE_DIR`, `base_dir` or a `stablemate_dir` checkout already names the base library. Under `--check` the call passes `refresh=False`: an absent base library is fetched and a present one stays at its current revision, because the check writes nothing and runs in CI. After a failed fetch install goes on to library resolution, which raises only when there is no overlay either.

The conflict scan runs before any prior output is deleted. Expected outputs are written in repo-relative path order. Ordinary output ends in one trailing newline, and an executable file keeps its executable permission. When the generated staged-files gate is among the outputs and repo scaffolding is enabled, install refreshes the QA-evidence ignore rules. When `managed.repo_scaffolding` is false it skips them, because the user-home install scope supplies no repository launcher output or hook manager. When the supplied hook manager is `none`, install strips Farrier's fenced hook entry from each supported manager file instead of adding one. When a `[user_library.<harness>]` table exists in the shared config, a repo install runs the [user install](#install---user) after it.

#### ownership

Install deletes what farrier generated and nothing else. The
[installation output ownership](concepts/installation-output-ownership.md) contract makes
ownership a property of the *file*, not of where it sits (`farrier/farrier/ownership.py`):

- a generated skill, prompt or command says so in its front matter —
  `metadata.generated_by: farrier`, see [generated-file metadata](formats/generated-file-metadata.md);
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

### install---user
- usage: `farrier install --user [--check] [--home DIR] [--library DIR]`
- flags:
  - `--user` — install into the harness home directories instead of a repo. Selection comes from
    the [shared config file](../workhorse/concepts/profiles-and-config.md), not from an `agents.yml`; no repo
    is read and none is written to.
  - `--home <dir>` — the home directory to install into. Default: `~`. It exists for tests and
    for a container that keeps its agent config somewhere other than `$HOME`.
  - `--check` — as for a repo install: verify the installed files are current, write nothing,
    exit `1` naming what would be rewritten.
  - `--library <dir>` — the same [layer resolution](concepts/library-directory.md) a repo install
    uses. User scope changes *where files land*, never where sources come from.
- does:
  - read `[user_library.<harness>]` from the config, one table per harness that gets a personal
    library, holding the same `skills:`/`prompts:`/`exclude:` keys
    [`agents.yml`](formats/agents-yml-config.md) uses
    - run: invoke(argv=["install", "--user", "--home", "c125/home", "--library", "c125/lib"], env={"HOME": "c125/home", "STABLEMATE_CONFIG": "c125/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c125/pipx-stub-bin:$PATH"})
    - verify: created(subject="c125/home/.claude/skills/demo/SKILL.md")
    - fixture: user-library-home dir=c125
  - install nothing for a harness that has no table
    - run: invoke(argv=["install", "--user", "--home", "c126/home", "--library", "c126/lib"], env={"HOME": "c126/home", "STABLEMATE_CONFIG": "c126/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c126/pipx-stub-bin:$PATH"})
    - verify: absent(subject="c126/home/.codex")
    - fixture: user-library-home dir=c126
  - exit with an error naming the config path when no user-library table exists, since `--user`
    was asked for explicitly
    - run: invoke(argv=["install", "--user", "--home", "c127/home", "--library", "c127/lib"], env={"HOME": "c127/home", "STABLEMATE_CONFIG": "c127/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c127/pipx-stub-bin:$PATH"})
    - verify: stderr(text="no user library is configured")
    - fixture: empty-repo-with-library dir=c127
  - install prompts only under Claude, the one harness with a personal command directory
    - run: invoke(argv=["install", "--user", "--home", "c128/home", "--library", "c128/lib"], env={"HOME": "c128/home", "STABLEMATE_CONFIG": "c128/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c128/pipx-stub-bin:$PATH"})
    - verify: created(subject="c128/home/.claude/commands/greet.md")
    - fixture: prompt-user-library-home dir=c128
  - skip a pack's prompts under any other harness, so one `packs = ["general"]` line serves both
    Claude and Codex
    - run: invoke(argv=["install", "--user", "--home", "c129/home", "--library", "c129/lib"], env={"HOME": "c129/home", "STABLEMATE_CONFIG": "c129/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c129/pipx-stub-bin:$PATH"})
    - verify: absent(subject="c129/home/.codex/commands")
    - fixture: pack-codex-home dir=c129
  - exit with an error when a non-Claude table names `prompts:`
    - run: invoke(argv=["install", "--user", "--home", "c130/home", "--library", "c130/lib"], env={"HOME": "c130/home", "STABLEMATE_CONFIG": "c130/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c130/pipx-stub-bin:$PATH"})
    - verify: stderr(text="Claude is the only harness with a personal command directory")
    - fixture: codex-prompts-home dir=c130
  - exit with an error when a table names `roots:`, because no harness reads a root instruction
    file from the home directory
    - run: invoke(argv=["install", "--user", "--home", "c131/home", "--library", "c131/lib"], env={"HOME": "c131/home", "STABLEMATE_CONFIG": "c131/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c131/pipx-stub-bin:$PATH"})
    - verify: stderr(text="names roots")
    - fixture: claude-roots-home dir=c131
  - exit with an error when a table selects no skills or prompts
    - run: invoke(argv=["install", "--user", "--home", "c132/home", "--library", "c132/lib"], env={"HOME": "c132/home", "STABLEMATE_CONFIG": "c132/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c132/pipx-stub-bin:$PATH"})
    - verify: stderr(text="selected no skills or prompts")
    - fixture: excluded-skill-home dir=c132
  - render each table's selection with a [`Renderer`](concepts/renderer.md) at user scope into
    `~/.claude/skills/<name>/SKILL.md`, `~/.claude/commands/<name>.md` and
    `~/.agents/skills/<name>/SKILL.md`
    - run: invoke(argv=["install", "--user", "--home", "c133/home", "--library", "c133/lib"], env={"HOME": "c133/home", "STABLEMATE_CONFIG": "c133/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c133/pipx-stub-bin:$PATH"})
    - verify: stdout(text="generated files into")
    - fixture: user-library-home dir=c133
  - install the Codex and Copilot tables as one union into `~/.agents/skills`, the home folder
    both harnesses read
    - run: invoke(argv=["install", "--user", "--home", "c134/home", "--library", "c134/lib"], env={"HOME": "c134/home", "STABLEMATE_CONFIG": "c134/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c134/pipx-stub-bin:$PATH"})
    - verify: created(subject="c134/home/.agents/skills/demo/SKILL.md")
    - fixture: codex-copilot-home dir=c134
  - sweep the farrier-generated skills an older install left in `~/.codex/skills` and
    `~/.copilot/skills`
    - run: invoke(argv=["install", "--user", "--home", "c135/home", "--library", "c135/lib"], env={"HOME": "c135/home", "STABLEMATE_CONFIG": "c135/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c135/pipx-stub-bin:$PATH"})
    - verify: removed(subject="c135/home/.codex/skills/old/SKILL.md")
    - fixture: codex-old-skill-home dir=c135
  - keep every hand-written file in `~/.codex/skills` and `~/.copilot/skills` during that sweep
    - run: invoke(argv=["install", "--user", "--home", "c136/home", "--library", "c136/lib"], env={"HOME": "c136/home", "STABLEMATE_CONFIG": "c136/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c136/pipx-stub-bin:$PATH"})
    - verify: unchanged(subject="c136/home/.codex/skills/mine/SKILL.md")
    - fixture: codex-hand-skill-home dir=c136
  - name each installed skill by its library folder alone (`stablemate/ostler` installs as
    `ostler`), never by a group or a repo, because a personal skill is the same skill in every
    checkout
    - run: invoke(argv=["install", "--user", "--home", "c137/home", "--library", "c137/lib"], env={"HOME": "c137/home", "STABLEMATE_CONFIG": "c137/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c137/pipx-stub-bin:$PATH"})
    - verify: created(subject="c137/home/.claude/skills/demo/SKILL.md")
    - fixture: grouped-user-library-home dir=c137
  - substitute `{{ template.* }}` from the shared `[user_library.template]` table
    - run: invoke(argv=["install", "--user", "--home", "c138/home", "--library", "c138/lib"], env={"HOME": "c138/home", "STABLEMATE_CONFIG": "c138/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c138/pipx-stub-bin:$PATH"})
    - verify: contents(subject="c138/home/.claude/skills/demo/SKILL.md", text="acme-value")
    - fixture: template-home dir=c138
  - reject an undefined `{{ template.* }}` reference as a hard error rather than rendering it
    empty
    - run: invoke(argv=["install", "--user", "--home", "c139/home", "--library", "c139/lib"], env={"HOME": "c139/home", "STABLEMATE_CONFIG": "c139/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c139/pipx-stub-bin:$PATH"})
    - verify: stderr(text="user_library.template")
    - fixture: undefined-template-home dir=c139
  - reject any `{{ repo.* }}` reference as a hard error because user scope has no repository to
    supply it
    - run: invoke(argv=["install", "--user", "--home", "c140/home", "--library", "c140/lib"], env={"HOME": "c140/home", "STABLEMATE_CONFIG": "c140/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c140/pipx-stub-bin:$PATH"})
    - verify: stderr(text="user scope")
    - fixture: repo-ref-home dir=c140
  - write no repo scaffolding: no launcher, no `.agents/` context manifest, no `.gitignore`
    rules, no aggregated `AGENTS.md`
    - run: invoke(argv=["install", "--user", "--home", "c141/home", "--library", "c141/lib"], env={"HOME": "c141/home", "STABLEMATE_CONFIG": "c141/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c141/pipx-stub-bin:$PATH"})
    - verify: absent(subject="c141/home/.agents/agents.mk")
    - fixture: user-library-home dir=c141
  - leave a hand-written `~/.claude/skills/mine/SKILL.md` in place across every install
    - run: invoke(argv=["install", "--user", "--home", "c142/home", "--library", "c142/lib"], env={"HOME": "c142/home", "STABLEMATE_CONFIG": "c142/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c142/pipx-stub-bin:$PATH"})
    - verify: unchanged(subject="c142/home/.claude/skills/mine/SKILL.md")
    - fixture: claude-hand-skill-home dir=c142
  - remove a farrier-generated skill the table no longer selects
    - run: invoke(argv=["install", "--user", "--home", "c143/home", "--library", "c143/lib"], env={"HOME": "c143/home", "STABLEMATE_CONFIG": "c143/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c143/pipx-stub-bin:$PATH"})
    - verify: removed(subject="c143/home/.claude/skills/old/SKILL.md")
    - fixture: claude-old-skill-home dir=c143
  - with `--check`, write nothing and report drift as a repo check does
    - run: invoke(argv=["install", "--user", "--check", "--home", "c144/home", "--library", "c144/lib"], env={"HOME": "c144/home", "STABLEMATE_CONFIG": "c144/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c144/pipx-stub-bin:$PATH"})
    - verify: stdout(text="missing: .claude/skills/demo/SKILL.md")
    - fixture: user-library-home dir=c144
  - refresh the user library after the repo install, on every repo install that is not `--check`,
    once a `[user_library.<harness>]` table exists, so the personal copy follows the library as a
    repo's does
    - run: invoke(argv=["install", "--repo", "c145", "--library", "c145/lib"], env={"HOME": "c145/home", "STABLEMATE_CONFIG": "c145/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c145/pipx-stub-bin:$PATH"})
    - verify: created(subject="c145/home/.claude/skills/demo/SKILL.md")
    - fixture: user-library-repo-home dir=c145
  - leave the home directory alone on a repo install when no table exists
    - run: invoke(argv=["install", "--repo", "c146", "--library", "c146/lib"], env={"HOME": "c146/home", "STABLEMATE_CONFIG": "c146/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c146/pipx-stub-bin:$PATH"})
    - verify: absent(subject="c146/home/.claude")
    - fixture: demo-skill-repo dir=c146
  - print one `info:` line before the install writes for each skill the repo selects that the
    user library also installs for an enabled harness, and keep the repo copy
    - run: invoke(argv=["install", "--repo", "c147", "--library", "c147/lib"], env={"HOME": "c147/home", "STABLEMATE_CONFIG": "c147/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c147/pipx-stub-bin:$PATH"})
    - verify: stdout(text="installs both in this repo and from the user library at home")
    - fixture: user-library-repo-home dir=c147
  - print no duplicate line under `--check`
    - run: invoke(argv=["install", "--check", "--repo", "c148", "--library", "c148/lib"], env={"HOME": "c148/home", "STABLEMATE_CONFIG": "c148/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c148/pipx-stub-bin:$PATH"})
    - verify: omits(subject="stdout", text="installs both in this repo")
    - fixture: user-library-repo-home dir=c148
- exits:
  - a user install returns `0` and prints `Installed <N> generated files into <home>`
    - run: invoke(argv=["install", "--user", "--home", "c149/home", "--library", "c149/lib"], env={"HOME": "c149/home", "STABLEMATE_CONFIG": "c149/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c149/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=0)
    - fixture: user-library-home dir=c149
  - a user install with no user library exits `1`
    - run: invoke(argv=["install", "--user", "--home", "c150/home", "--library", "c150/lib"], env={"HOME": "c150/home", "STABLEMATE_CONFIG": "c150/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c150/pipx-stub-bin:$PATH"})
    - verify: exit_status(code=1)
    - fixture: empty-repo-with-library dir=c150
- code: `farrier/farrier/cli.py::_run_user_install` @0244d6a97e3b
- code: `farrier/farrier/outputs.py::render_user_expected` @0b63626747f4
- tests: `farrier/tests/test_user_install.py::test_skills_and_prompts_land_in_the_harness_home`
- tests: `farrier/tests/test_user_install.py::test_the_repo_scaffolding_stays_out_of_the_home`
- tests: `farrier/tests/test_user_install.py::test_a_deselected_skill_is_swept_and_a_hand_written_one_is_not`
- tests: `farrier/tests/test_user_install.py::test_prompts_under_a_non_claude_harness_are_an_error`
- tests: `farrier/tests/test_user_install.py::test_a_pack_under_a_non_claude_harness_installs_its_skills_only`
- tests: `farrier/tests/test_user_install.py::test_codex_and_copilot_install_the_union_of_their_tables_into_one_folder`
- tests: `farrier/tests/test_user_install.py::test_a_skill_left_in_the_old_codex_and_copilot_folders_is_swept`
- tests: `farrier/tests/test_user_install.py::test_a_repo_install_also_refreshes_the_user_library`
- tests: `farrier/tests/test_user_install.py::test_a_repo_install_leaves_the_home_alone_without_a_user_library`
- tests: `farrier/tests/test_user_install.py::test_a_repo_check_never_writes_the_user_library`
- tests: `farrier/tests/test_user_install.py::test_a_repo_install_names_each_skill_the_home_also_installs`
- tests: `farrier/tests/test_user_install.py::test_a_home_copy_for_a_harness_the_repo_does_not_enable_is_no_duplicate`
- tests: `farrier/tests/test_user_install.py::test_a_repo_check_prints_no_duplicate_notice`
