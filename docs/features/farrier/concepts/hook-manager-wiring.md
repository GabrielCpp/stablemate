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

- code: `farrier/farrier/hook_managers.py`
- tests: `farrier/tests/test_hook_managers.py`
- detail: [skill hook declarations](skill-hook-declarations.md)

## Fields

### HOOK_COMMAND
- type: `str`
- default: `make farrier-run-hook`
- required: true
- semantics: the sole command delegated by every generated manager entry and runner
- verify: count(subject="hook-manager generated command", equals=1)
- code: `farrier/farrier/hook_managers.py::HOOK_COMMAND`

### FENCE_START
- type: `str`
- default: `# >>> farrier: hooks (generated) >>>`
- required: true
- semantics: the line beginning Farrier's replaceable ownership region
- verify: count(subject="hook fence start marker", equals=1)
- code: `farrier/farrier/hook_managers.py::FENCE_START`

### FENCE_END
- type: `str`
- default: `# <<< farrier: hooks <<<`
- required: true
- semantics: the line ending Farrier's replaceable ownership region
- verify: count(subject="hook fence end marker", equals=1)
- code: `farrier/farrier/hook_managers.py::FENCE_END`

### HOOK_RUNNER
- type: `str`
- default: `.agents/hooks/pre-commit`
- required: true
- semantics: the generated per-repository script that runs selected skill hooks
- verify: count(subject="generated hook runner path", equals=1)
- code: `farrier/farrier/hook_managers.py::HOOK_RUNNER`

### LEFTHOOK_INCLUDE
- type: `str`
- default: `.agents/lefthook.farrier.yml`
- required: true
- semantics: the Farrier-owned lefthook file referenced by the user's lefthook configuration
- verify: count(subject="lefthook Farrier include path", equals=1)
- code: `farrier/farrier/hook_managers.py::LEFTHOOK_INCLUDE`

### MANAGERS
- type: `tuple[str, ...]`
- default: `pre-commit | lefthook | husky | githooks | none`
- required: true
- semantics: the complete accepted hook-manager vocabulary
- verify: count(subject="accepted hook managers", equals=5)
- code: `farrier/farrier/hook_managers.py::MANAGERS`

### LEGACY_HOOK_MARKER
- type: `str`
- default: `# >>> farrier: staged-files gate (generated) >>>`
- required: true
- semantics: the marker identifying a pre-fence whole-file hook that must be migrated
- verify: count(subject="legacy hook migration marker", equals=1)
- code: `farrier/farrier/hook_managers.py::LEGACY_HOOK_MARKER`

## Methods

### configured_manager
- sig: `configured_manager(config: dict[str, Any], repo: Path) -> str`
- does: reads `hooks.manager` when it is a mapping value with non-whitespace content
- does: falls back to repository detection when `hooks.manager` is absent, empty, or not a mapping
- raises: `SystemExit` when a declared manager is outside `MANAGERS`, naming the invalid value and accepted managers
- returns: the declared or detected manager name
- verify: count(subject="configured manager selected from agents.yml", equals=1)
- verify: count(subject="invalid configured manager rejection", equals=1)
- code: `farrier/farrier/hook_managers.py::configured_manager`
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
- code: `farrier/farrier/hook_managers.py::detect_manager`
- tests: `farrier/tests/test_hook_managers.py::test_an_unconfigured_repo_falls_back_to_what_it_looks_like`
- tests: `farrier/tests/test_hook_managers.py::test_a_bare_repo_detects_as_githooks`
- tests: `farrier/tests/test_hook_managers.py::test_husky_is_detected_before_npm_install_has_run`

### fence
- sig: `fence(body: str) -> str`
- does: wraps the trimmed body between the exact start and end markers
- returns: a fenced block ending in one newline
- verify: count(subject="fence marker pair", equals=1)
- code: `farrier/farrier/hook_managers.py::fence`

### splice
- sig: `splice(existing: str, block: str) -> str`
- does: replaces the existing marker-bounded region in place when both markers are present
- does: appends the block after the existing text when no complete fence is present
- returns: text with one trailing newline and all non-fenced lines preserved
- verify: unchanged(subject="user-owned lines outside hook fence")
- code: `farrier/farrier/hook_managers.py::splice`
- tests: `farrier/tests/test_hook_managers.py::test_the_fence_is_replaced_in_place_not_appended`

### unsplice
- sig: `unsplice(existing: str) -> str`
- does: removes the marker-bounded region when both markers are present
- does: returns the input unchanged when no complete fence is present
- returns: the remaining text with one trailing newline, or an empty string when nothing remains
- verify: unchanged(subject="user-owned lines after fence removal")
- code: `farrier/farrier/hook_managers.py::unsplice`
- tests: `farrier/tests/test_hook_managers.py::test_unsplicing_leaves_the_rest_of_the_file`

### fenced_body
- sig: `fenced_body(existing: str) -> str | None`
- does: extracts only the lines between the first start and end markers
- does: treats an absent start or end marker as an unfenced file
- returns: the fenced body, or `None` when no complete fence exists
- verify: count(subject="fenced body extraction result", equals=1)
- code: `farrier/farrier/hook_managers.py::fenced_body`

### body_for
- sig: `body_for(manager: str) -> str`
- does: returns a pre-commit local-repository hook entry for `pre-commit`
- does: returns a lefthook `extends` reference for `lefthook`
- does: returns the shell command for `husky`, `githooks`, and other non-special manager values
- returns: the manager-specific fence body
- verify: count(subject="manager-specific fence bodies", equals=3)
- code: `farrier/farrier/hook_managers.py::body_for`

### lefthook_include_text
- sig: `lefthook_include_text() -> str`
- returns: the complete generated lefthook configuration defining the `pre-commit` Farrier command
- verify: visible(locator="lefthook include text", text="farrier-hooks")
- code: `farrier/farrier/hook_managers.py::lefthook_include_text`
- tests: `farrier/tests/test_hook_managers.py::test_lefthook_references_a_file_farrier_owns_whole`

### runner_text
- sig: `runner_text(hooks: list[SkillHook]) -> str`
- does: emits a shell runner with strict failure handling and the repository root resolved from git
- does: checks each selected skill hook in selection order across `.claude/skills`, `.agents/skills`, and `.github/skills`
- does: runs the first existing adapter script for each hook and proceeds to the next hook
- does: emits a successful no-hook runner that exits zero when no skill declares a pre-commit hook
- does: invokes each found adapter with `python3`
- does: stops searching that hook's three adapter paths after the first found file
- returns: generated `.agents/hooks/pre-commit` text
- verify: visible(locator="generated hook runner", text="git rev-parse --show-toplevel")
- code: `farrier/farrier/hook_managers.py::runner_text`
- tests: `farrier/tests/test_hook_managers.py::test_the_runner_tries_every_adapter_path_for_a_declared_hook`
- tests: `farrier/tests/test_hook_managers.py::test_a_repo_whose_skills_declare_nothing_still_gets_a_runner`

### install_manager
- sig: `install_manager(repo: Path, manager: str) -> list[str]`
- does: removes Farrier's fence from every supported manager file and writes nothing when `manager` is `none`
- does: migrates a legacy whole-file Farrier hook by discarding it before writing the fenced hook
- does: creates an empty shell preamble for a missing `husky` or `githooks` hook
- does: writes the manager-specific fenced entry while preserving user-owned surrounding lines
- does: ensures a new pre-commit configuration begins with `repos:` when absent
- does: makes `husky` and `githooks` hook files executable
- does: sets `core.hooksPath` to `.githooks` for `githooks`
- returns: messages for changed or removed files, and an empty list when installation changes nothing
- verify: removed(subject="Farrier fenced hook entry when manager is none")
- verify: unchanged(subject="user-owned hook-manager lines")
- verify: persists(subject="githooks core.hooksPath")
- code: `farrier/farrier/hook_managers.py::install_manager`
- tests: `farrier/tests/test_hook_managers.py::test_every_manager_gets_the_command_and_keeps_the_users_lines`
- tests: `farrier/tests/test_hook_managers.py::test_installing_twice_changes_nothing`
- tests: `farrier/tests/test_hook_managers.py::test_a_shell_hook_farrier_creates_is_executable`
- tests: `farrier/tests/test_hook_managers.py::test_githooks_points_git_at_the_tracked_directory`
- tests: `farrier/tests/test_hook_managers.py::test_a_legacy_whole_file_hook_is_migrated_not_appended_to`
- tests: `farrier/tests/test_hook_managers.py::test_none_removes_the_entry_and_leaves_the_file`

### fence_drift
- sig: `fence_drift(repo: Path, manager: str) -> list[str]`
- does: reports every supported file still carrying a Farrier fence when the manager is `none`
- does: reports the configured manager file when it is missing or its fenced body differs from the desired body
- does: ignores changes outside the Farrier fence
- returns: repository-relative paths with drift, or an empty list when the installed fence matches
- verify: count(subject="missing or edited hook fences reported as drift", equals=1)
- verify: count(subject="user-owned edits outside hook fences reported as drift", equals=0)
- code: `farrier/farrier/hook_managers.py::fence_drift`
- tests: `farrier/tests/test_hook_managers.py::test_a_missing_fence_is_drift_not_an_opt_out`
- tests: `farrier/tests/test_hook_managers.py::test_an_edit_inside_the_fence_is_drift`
- tests: `farrier/tests/test_hook_managers.py::test_an_edit_outside_the_fence_is_not`
- tests: `farrier/tests/test_hook_managers.py::test_a_leftover_fence_is_drift_under_none`
