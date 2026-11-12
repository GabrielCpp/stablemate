---
type: concept
slug: hook-manager-wiring
title: Hook manager wiring
---
# Hook manager wiring

Farrier owns one fenced region in the repository's hook-manager file. The surrounding file remains
operator-owned, while the region always delegates to `make farrier-run-hook`. `agents.yml` may
name `pre-commit`, `lefthook`, `husky`, `githooks`, or `none`; when it omits the setting, Farrier
detects the manager from repository marker files.

The `none` value removes Farrier's fence from every supported manager file. Deleting a fence by
hand is not an opt-out: the configured manager still expects it and reports drift. Legacy
whole-file Farrier hooks are replaced before the new fence is written so the old gate cannot run
twice.

A skill's hook script runs under the system `python3` with the standard library only, so it
cannot import the stablemate core to find the shared cache. The runner hands it the location
instead. A hook that needs a tool, such as a clone detector, fetches it once into that cache and
reuses it across repositories.

Farrier wires two stages. The `pre-commit` stage runs `.agents/hooks/pre-commit`, and the
`commit-msg` stage runs `.agents/hooks/commit-msg` with the message file. Each runner holds the
hooks that the installed skills and policies declare for its stage. A person's commit pays for
these runners only. The slow checks, such as the drift check and a sweep for private names, run
from an agent's commit through the [agent commit checks](agent-commit-checks.md) instead.

- code: `farrier/farrier/hook_managers.py` @d3dc4b579f47
- rule: a skill hook script reads the shared cache location from `STABLEMATE_CACHE_DIR`, which the generated runner exports; it never derives the path itself
- rule: a machine without `farrier` on its `PATH` passes the runner, because a generated runner may reach a clone on a machine that has no farrier
- rule: the generated runner never calls farrier, because a person's commit must not pay for the drift check or for the user library's checks
- rule: a hook belongs in a git hook only when it is fast and must hold for every committer, such as the commit-message format, and every other check is a commit check an agent's commit runs
- rule: every shell manager wires `commit-msg` beside `pre-commit`, and the `commit-msg` entry passes when the repository has no message runner
- tests: `farrier/tests/test_hook_managers.py`
- detail: [skill hook declarations](skill-hook-declarations.md)

## Fields

### HOOK_COMMAND
- type: `str`
- default: `make farrier-run-hook`
- required: true
- semantics: the sole command delegated by every generated manager entry and runner
- verify: count(subject="hook-manager generated command", equals=1)
- code: `farrier/farrier/hook_managers.py::HOOK_COMMAND` @d3dc4b579f47

### FENCE_START
- type: `str`
- default: `# >>> farrier: hooks (generated) >>>`
- required: true
- semantics: the line beginning Farrier's replaceable ownership region
- verify: count(subject="hook fence start marker", equals=1)
- code: `farrier/farrier/hook_managers.py::FENCE_START` @d3dc4b579f47

### FENCE_END
- type: `str`
- default: `# <<< farrier: hooks <<<`
- required: true
- semantics: the line ending Farrier's replaceable ownership region
- verify: count(subject="hook fence end marker", equals=1)
- code: `farrier/farrier/hook_managers.py::FENCE_END` @d3dc4b579f47

### HOOK_RUNNER
- type: `str`
- default: `.agents/hooks/pre-commit`
- required: true
- semantics: the generated per-repository script that runs the selected `pre-commit` hooks
- verify: count(subject="generated hook runner path", equals=1)
- code: `farrier/farrier/hook_managers.py::HOOK_RUNNER` @d3dc4b579f47

### MESSAGE_RUNNER
- type: `str`
- default: `.agents/hooks/commit-msg`
- required: true
- semantics: the generated per-repository script that runs the selected `commit-msg` hooks with the message file
- verify: count(subject="generated message runner path", equals=1)
- code: `farrier/farrier/hook_managers.py::MESSAGE_RUNNER` @d3dc4b579f47

### RUNNERS
- type: `dict[str, str]`
- default: `pre-commit` to `.agents/hooks/pre-commit`, `commit-msg` to `.agents/hooks/commit-msg`
- required: true
- semantics: the runner path of each wired stage
- verify: count(subject="wired stages with a runner", equals=2)
- code: `farrier/farrier/hook_managers.py::RUNNERS` @d3dc4b579f47

### LEFTHOOK_INCLUDE
- type: `str`
- default: `.agents/lefthook.farrier.yml`
- required: true
- semantics: the Farrier-owned lefthook file referenced by the user's lefthook configuration
- verify: count(subject="lefthook Farrier include path", equals=1)
- code: `farrier/farrier/hook_managers.py::LEFTHOOK_INCLUDE` @d3dc4b579f47

### MANAGERS
- type: `tuple[str, ...]`
- default: `pre-commit | lefthook | husky | githooks | none`
- required: true
- semantics: the complete accepted hook-manager vocabulary
- verify: count(subject="accepted hook managers", equals=5)
- code: `farrier/farrier/hook_managers.py::MANAGERS` @d3dc4b579f47

### LEGACY_HOOK_MARKER
- type: `str`
- default: `# >>> farrier: staged-files gate (generated) >>>`
- required: true
- semantics: the marker identifying a pre-fence whole-file hook that must be migrated
- verify: count(subject="legacy hook migration marker", equals=1)
- code: `farrier/farrier/hook_managers.py::LEGACY_HOOK_MARKER` @d3dc4b579f47

## Methods

### configured_manager
- sig: `configured_manager(config: dict[str, Any], repo: Path) -> str`
- does: reads `hooks.manager` when it is a mapping value with non-whitespace content
- verify: count(subject="configured manager selected from agents.yml", equals=1)
- does: falls back to repository detection when `hooks.manager` is absent, empty, or not a mapping
- raises: `SystemExit` when a declared manager is outside `MANAGERS`, naming the invalid value and accepted managers
- verify: count(subject="invalid configured manager rejection", equals=1)
- returns: the declared or detected manager name
- code: `farrier/farrier/hook_managers.py::configured_manager` @8e263f4c320f
- tests: `farrier/tests/test_hook_managers.py::test_the_config_names_the_manager`
- tests: `farrier/tests/test_hook_managers.py::test_a_manager_outside_the_vocabulary_is_refused`

### detect_manager
- sig: `detect_manager(repo: Path) -> str`
- does: selects `pre-commit` when either `.pre-commit-config.yaml` or `.pre-commit-config.yml` exists
- does: selects `lefthook` when any supported lefthook YAML marker exists
- does: selects `husky` when `.husky` is a directory or `package.json` contains `husky`
- does: selects `githooks` when no earlier marker identifies another manager
- returns: the first matching manager without relying on `core.hooksPath` alone
- verify: count(subject="marker-based hook manager detection", equals=1)
- code: `farrier/farrier/hook_managers.py::detect_manager` @3416ac1480f4
- tests: `farrier/tests/test_hook_managers.py::test_an_unconfigured_repo_falls_back_to_what_it_looks_like`
- tests: `farrier/tests/test_hook_managers.py::test_a_bare_repo_detects_as_githooks`
- tests: `farrier/tests/test_hook_managers.py::test_husky_is_detected_before_npm_install_has_run`

### fence
- sig: `fence(body: str) -> str`
- does: wraps the trimmed body between the exact start and end markers
- returns: a fenced block ending in one newline
- verify: count(subject="fence marker pair", equals=1)
- code: `farrier/farrier/hook_managers.py::fence` @bec6a8828535

### splice
- sig: `splice(existing: str, block: str) -> str`
- does: replaces the existing marker-bounded region in place when both markers are present
- does: appends the block after the existing text when no complete fence is present
- returns: text with one trailing newline and all non-fenced lines preserved
- verify: unchanged(subject="user-owned lines outside hook fence")
- code: `farrier/farrier/hook_managers.py::splice` @f434b3857085
- tests: `farrier/tests/test_hook_managers.py::test_the_fence_is_replaced_in_place_not_appended`

### unsplice
- sig: `unsplice(existing: str) -> str`
- does: removes the marker-bounded region when both markers are present
- does: returns the input unchanged when no complete fence is present
- returns: the remaining text with one trailing newline, or an empty string when nothing remains
- verify: unchanged(subject="user-owned lines after fence removal")
- code: `farrier/farrier/hook_managers.py::unsplice` @48b8e50659dd
- tests: `farrier/tests/test_hook_managers.py::test_unsplicing_leaves_the_rest_of_the_file`

### fenced_body
- sig: `fenced_body(existing: str) -> str | None`
- does: extracts only the lines between the first start and end markers
- does: treats an absent start or end marker as an unfenced file
- returns: the fenced body, or `None` when no complete fence exists
- verify: count(subject="fenced body extraction result", equals=1)
- code: `farrier/farrier/hook_managers.py::fenced_body` @3d8dd0c6f763

### body_for
- sig: `body_for(manager: str, rel: str = "") -> str`
- does: returns a pre-commit local-repository entry for each of the two stages for `pre-commit`
- does: returns a lefthook `extends` reference for `lefthook`
- does: returns the command that runs `.agents/hooks/commit-msg` with the message file when `rel` names a `commit-msg` hook file
- does: returns the shell command for any other `husky` or `githooks` hook file
- returns: the manager-specific fence body
- verify: count(subject="manager-specific fence bodies", equals=3)
- code: `farrier/farrier/hook_managers.py::body_for` @521bb34f8ff2

### lefthook_include_text
- sig: `lefthook_include_text() -> str`
- returns: the complete generated lefthook configuration defining the `pre-commit` Farrier command
- verify: json_path(path="return value", matches="farrier-hooks")
- code: `farrier/farrier/hook_managers.py::lefthook_include_text` @c53d12a8ef56
- tests: `farrier/tests/test_hook_managers.py::test_lefthook_references_a_file_farrier_owns_whole`

### runner_text
- sig: `runner_text(hooks: list[SkillHook], stage: str = "pre-commit") -> str`
- does: keeps only the hooks declared for `stage`
- does: emits a shell runner with strict failure handling and the repository root resolved from git
- does: checks each skill hook in selection order across `.claude/skills`, `.agents/skills`, and `.github/skills`
- does: checks each policy hook under `.agents/policies`
- does: runs the first existing script for each hook and proceeds to the next hook
- does: emits a successful runner that says `# No installed skill declares a <stage> hook.` when no hook is declared for the stage
- does: exports `STABLEMATE_CACHE_DIR` before the first hook, defaulting it to the stablemate cache root and keeping a value already set in the environment
- does: exports nothing in the no-hook runner
- does: invokes a `.py` script with `python3` and any other script directly, passing the runner's own arguments
- does: stops searching that hook's paths after the first found file
- returns: generated `.agents/hooks/<stage>` text
- verify: json_path(path="return value", matches="git rev-parse --show-toplevel")
- code: `farrier/farrier/hook_managers.py::runner_text` @a3c16d45bb5c
- tests: `farrier/tests/test_hook_managers.py::test_the_runner_tries_every_adapter_path_for_a_declared_hook`
- tests: `farrier/tests/test_hook_managers.py::test_a_repo_whose_skills_declare_nothing_still_gets_a_runner`
- tests: `farrier/tests/test_hook_managers.py::test_the_runner_exports_the_cache_dir_before_the_first_gate`
- tests: `farrier/tests/test_hook_managers.py::test_the_empty_runner_exports_nothing`
- tests: `farrier/tests/test_hook_managers.py::test_the_runner_leaves_farrier_out_of_a_human_commit`
- tests: `farrier/tests/test_hook_managers.py::test_the_message_runner_runs_only_commit_msg_hooks`

### install_manager
- sig: `install_manager(repo: Path, manager: str, *, dry_run: bool = False) -> list[str]`
- does: removes Farrier's fence from every supported manager file and writes nothing when `manager` is `none`
- verify: removed(subject="Farrier fenced hook entry when manager is none")
- does: migrates a legacy whole-file Farrier hook by discarding it before writing the fenced hook
- does: creates an empty shell preamble for a missing `husky` or `githooks` hook
- does: writes the manager-specific fenced entry while preserving user-owned surrounding lines
- verify: unchanged(subject="user-owned hook-manager lines")
- does: ensures a new pre-commit configuration begins with `repos:` when absent
- does: makes `husky` and `githooks` hook files executable
- does: sets `core.hooksPath` to `.githooks` for `githooks`
- verify: persists(subject="githooks core.hooksPath")
- does: writes nothing and prefixes every message with `[dry-run] ` when `dry_run` is true
- returns: messages for changed or removed files, and an empty list when installation changes nothing
- code: `farrier/farrier/hook_managers.py::install_manager` @244c3af883d1
- tests: `farrier/tests/test_hook_managers.py::test_every_manager_gets_the_command_and_keeps_the_users_lines`
- tests: `farrier/tests/test_hook_managers.py::test_installing_twice_changes_nothing`
- tests: `farrier/tests/test_hook_managers.py::test_a_shell_hook_farrier_creates_is_executable`
- tests: `farrier/tests/test_hook_managers.py::test_githooks_points_git_at_the_tracked_directory`
- tests: `farrier/tests/test_hook_managers.py::test_a_legacy_whole_file_hook_is_migrated_not_appended_to`
- tests: `farrier/tests/test_hook_managers.py::test_none_removes_the_entry_and_leaves_the_file`
- tests: `farrier/tests/test_hook_managers.py::test_githooks_wires_the_commit_msg_stage`
- tests: `farrier/tests/test_hook_managers.py::test_husky_wires_the_commit_msg_stage`

### install_runner
- sig: `install_runner(repo: Path, hooks: list[SkillHook] | None, *, dry_run: bool = False) -> list[str]`
- does: writes each stage's runner from `RUNNERS` from the declared hooks and makes it executable when the file differs
- does: leaves a runner alone and reports nothing when its text already matches
- does: reports each runner that would be regenerated, and writes nothing, when `dry_run` is true
- does: reports that the runners cannot be built without a library, and writes nothing, when `hooks` is `None` under `dry_run`
- returns: one `Wrote <runner>` line per runner it wrote, and an empty list otherwise
- verify: created(subject=".agents/hooks/pre-commit")
- code: `farrier/farrier/hook_managers.py::install_runner` @b36582f482f3

### fence_drift
- sig: `fence_drift(repo: Path, manager: str) -> list[str]`
- does: reports every supported file still carrying a Farrier fence when the manager is `none`
- does: reports the configured manager file when it is missing or its fenced body differs from the desired body
- verify: count(subject="missing or edited hook fences reported as drift", equals=1)
- does: ignores changes outside the Farrier fence
- verify: count(subject="user-owned edits outside hook fences reported as drift", equals=0)
- returns: repository-relative paths with drift, or an empty list when the installed fence matches
- code: `farrier/farrier/hook_managers.py::fence_drift` @5eae8472a455
- tests: `farrier/tests/test_hook_managers.py::test_a_missing_fence_is_drift_not_an_opt_out`
- tests: `farrier/tests/test_hook_managers.py::test_an_edit_inside_the_fence_is_drift`
- tests: `farrier/tests/test_hook_managers.py::test_an_edit_outside_the_fence_is_not`
- tests: `farrier/tests/test_hook_managers.py::test_a_leftover_fence_is_drift_under_none`
