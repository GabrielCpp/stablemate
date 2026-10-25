---
type: concept
slug: output-installation
title: Output installation
---
# Output installation

Output installation turns rendered content into a safe, idempotent repository update. It checks
ownership before deletion, removes only Farrier-owned files, writes deterministic output, and then
maintains repository integration files.

### method: Managed
- sig: `Managed(dirs: tuple[str, ...], files: tuple[str, ...] = (), assumed: tuple[str, ...] = (), repo_scaffolding: bool = True)`
- does: define the directories, files, convention-owned paths, and repository upkeep owned by one install scope
- code: `farrier/farrier/outputs.py::Managed` @0b63626747f4
- verify: count(subject="output ownership scopes", equals=1)

## Methods

### method: expected_text
- sig: `expected_text(content: str) -> str`
- does: normalize ordinary generated content to one trailing newline while preserving verbatim output
- verify: count(subject="ordinary output trailing newlines", equals=1)
- code: `farrier/farrier/outputs.py::expected_text` @a2464a92144d

### method: write_text
- sig: `write_text(path: Path, content: str) -> None`
- does: create parent directories, write normalized UTF-8 text, and preserve executable intent
- verify: created(subject="written generated output")
- code: `farrier/farrier/outputs.py::write_text` @a2464a92144d

### method: normalize_agents
- sig: `normalize_agents(config: dict[str, Any]) -> dict[str, bool]`
- does: normalize list or mapping agent declarations to codex, claude, and copilot booleans
- verify: count(subject="normalized agent flags", equals=3)
- code: `farrier/farrier/outputs.py::normalize_agents` @0b63626747f4

### method: is_assumed_owned
- sig: `is_assumed_owned(repo: Path, path: Path, managed: Managed = REPO_MANAGED) -> bool`
- does: identify convention-owned paths exempt from marker-based ownership checks
- verify: count(subject="assumed-owned output path matches", equals=1)
- code: `farrier/farrier/outputs.py::is_assumed_owned` @a2464a92144d

### method: conflicts
- sig: `conflicts(repo: Path, outputs: dict[Path, str], managed: Managed = REPO_MANAGED) -> list[str]`
- does: return sorted output paths held by unowned existing files
- verify: count(subject="unowned output conflicts", equals=1)
- code: `farrier/farrier/outputs.py::conflicts` @0b63626747f4

### method: refuse_conflicts
- sig: `refuse_conflicts(repo: Path, outputs: dict[Path, str], managed: Managed = REPO_MANAGED) -> None`
- does: abort before mutation when any output conflicts with an unowned file
- raises: `SystemExit` naming every conflicting path
- verify: unchanged(subject="repository after unowned-output refusal")
- code: `farrier/farrier/outputs.py::refuse_conflicts` @0b63626747f4

### method: remove_targets
- sig: `remove_targets(repo: Path, managed: Managed = REPO_MANAGED) -> None`
- does: delete only marked or convention-owned previous outputs and assumed-owned empty artifacts
- verify: removed(subject="deselected Farrier-owned output")
- code: `farrier/farrier/outputs.py::remove_targets` @0b63626747f4
- detail: [output cleanup selection](output-cleanup-selection.md)

### method: check_selection
- sig: `check_selection(groups: list[tuple[str, list, set[str]]]) -> None`
- does: reject unmatched literal selections and warn for unmatched globs
- verify: exit_status(code=1)
- code: `farrier/farrier/outputs.py::check_selection` @a2464a92144d

### method: render_expected
- sig: `render_expected(config: dict[str, Any], repo: Path, instructions: Sequence[LocalInstruction], notices: list[str] | None = None) -> dict[Path, str]`
- does: resolve configured selections into the expected output set
- verify: count(subject="expected repository outputs", equals=1)
- does: validate selections before rendering outputs
- verify: exit_status(code=1)
- does: render the selected adapters
- verify: count(subject="rendered adapter outputs", equals=1)
- does: render the AGENTS.md of each local instruction for its configured paths, and a CLAUDE.md beside it when the instruction writes one
- verify: count(subject="rendered local instruction outputs", equals=1)
- does: add hook outputs when a manager is configured
- verify: count(subject="configured hook outputs", equals=1)
- does: append an info line to `notices` for each selected skill the user library also installs for an enabled harness
- verify: count(subject="home duplicate notices", equals=1)
- code: `farrier/farrier/outputs.py::render_expected` @0b63626747f4

### method: repo_managed_with_claude_pointers
- sig: `repo_managed_with_claude_pointers(instructions: Sequence[LocalInstruction]) -> Managed`
- does: extend the repository scope with the CLAUDE.md of every local instruction directory so cleanup can remove it
- verify: count(subject="local instruction CLAUDE.md cleanup paths", equals=1)
- code: `farrier/farrier/outputs.py::repo_managed_with_claude_pointers` @0b63626747f4

### method: home_duplicate_notices
- sig: `home_duplicate_notices(skills: Sequence[Source], home_skills: dict[str, list[Source]], agents: dict[str, Any]) -> list[str]`
- does: return one info line per selected skill that the user library also installs for an enabled harness
- verify: count(subject="home duplicate notices", equals=1)
- code: `farrier/farrier/outputs.py::home_duplicate_notices` @0b63626747f4

### method: user_selections
- sig: `user_selections(config: dict[str, Any], all_skills: list[Source], all_prompts: list[Source]) -> dict[str, tuple[list[Source], list[Source]]]`
- does: select each harness's user-library skills and prompts from the stablemate config
- verify: count(subject="user-library harness selections", equals=1)
- raises: `SystemExit` when a non-Claude harness names prompts
- verify: exit_status(code=1)
- code: `farrier/farrier/outputs.py::user_selections` @a2464a92144d

### method: share_home_folders
- sig: `share_home_folders(selections: dict[str, tuple[list[Source], list[Source]]]) -> dict[str, tuple[list[Source], list[Source]]]`
- does: widen each harness's selection to the union of every harness that installs into the same home folder
- verify: count(subject="shared home folder selections", equals=1)
- code: `farrier/farrier/outputs.py::share_home_folders` @a2464a92144d

### method: render_user_expected
- sig: `render_user_expected(config: dict[str, Any], home: Path) -> dict[Path, str]`
- does: render configured user-scope harness selections without repository scaffolding, once per home folder that several harnesses share
- verify: absent(subject="repository scaffolding in user-scope output map")
- code: `farrier/farrier/outputs.py::render_user_expected` @a2464a92144d

### method: selected_hooks
- sig: `selected_hooks(prefix: str, skills) -> list[SkillHook]`
- does: collect hooks declared by selected library skills in selection order
- verify: count(subject="selected skill hooks", equals=1)
- code: `farrier/farrier/outputs.py::selected_hooks` @a2464a92144d

### method: check_outputs
- sig: `check_outputs(repo: Path, outputs: dict[Path, str], manager: str | None = None, managed: Managed = REPO_MANAGED) -> int`
- does: report missing, changed, extra, and hook-fence drift without writing
- returns: `1` when any drift exists and `0` otherwise
- verify: unchanged(subject="repository after output check")
- code: `farrier/farrier/outputs.py::check_outputs` @0b63626747f4

### method: ensure_gitignore_entry
- sig: `ensure_gitignore_entry(repo: Path, entry: str) -> bool`
- does: append one exact ignore entry with separation and no duplicate
- verify: count(subject="duplicate gitignore entries", equals=0)
- code: `farrier/farrier/managed_blocks.py::ensure_gitignore_entry` @5e7d36ee4e99

### method: ensure_agents_gitignore
- sig: `ensure_agents_gitignore(repo: Path) -> bool`
- does: replace superseded `.agents` ignore spellings with the current managed block, which also ignores the generated `.agents/agents.mk`
- verify: count(subject="managed agents gitignore block", equals=1)
- code: `farrier/farrier/managed_blocks.py::ensure_agents_gitignore` @5e7d36ee4e99

### method: ensure_makefile_include
- sig: `ensure_makefile_include(repo: Path) -> bool`
- does: append a marked optional `-include` of the launcher to an existing root Makefile without replacing its content
- verify: count(subject="generated launcher include blocks", equals=1)
- does: rewrite an existing marked block in place so an older `include` line becomes `-include`
- verify: count(subject="upgraded launcher include lines", equals=1)
- does: leave the Makefile unchanged when a bare include of the launcher is already present
- verify: unchanged(subject="root Makefile with a bare launcher include")
- code: `farrier/farrier/managed_blocks.py::ensure_makefile_include` @5e7d36ee4e99

### method: install_outputs
- sig: `install_outputs(repo: Path, outputs: dict[Path, str], manager: str | None = None, managed: Managed = REPO_MANAGED) -> None`
- does: refuse installation when outputs conflict with unowned files
- verify: unchanged(subject="repository after unowned-output refusal")
- does: remove old owned outputs before installation
- verify: removed(subject="deselected Farrier-owned output")
- does: write the generated output set in path order
- verify: created(subject="installed generated output set")
- does: update ignore integration for generated agent and QA artifacts
- verify: count(subject="managed output ignore blocks", equals=2)
- does: update hook integration when a manager is configured
- verify: count(subject="managed hook integration entries", equals=1)
- does: update Makefile integration for generated launcher outputs
- verify: count(subject="generated launcher include blocks", equals=1)
- code: `farrier/farrier/outputs.py::install_outputs` @0b63626747f4
