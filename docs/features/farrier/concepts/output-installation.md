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
- code: `farrier/farrier/outputs.py::Managed`
- verify: count(subject="output ownership scopes", equals=1)

## Methods

### method: expected_text
- sig: `expected_text(content: str) -> str`
- does: normalize ordinary generated content to one trailing newline while preserving verbatim output
- verify: count(subject="ordinary output trailing newlines", equals=1)
- code: `farrier/farrier/outputs.py::expected_text`

### method: write_text
- sig: `write_text(path: Path, content: str) -> None`
- does: create parent directories, write normalized UTF-8 text, and preserve executable intent
- verify: created(subject="written generated output")
- code: `farrier/farrier/outputs.py::write_text`

### method: normalize_agents
- sig: `normalize_agents(config: dict[str, Any]) -> dict[str, bool]`
- does: normalize list or mapping agent declarations to codex, claude, and copilot booleans
- verify: count(subject="normalized agent flags", equals=3)
- code: `farrier/farrier/outputs.py::normalize_agents`

### method: is_assumed_owned
- sig: `is_assumed_owned(repo: Path, path: Path, managed: Managed = REPO_MANAGED) -> bool`
- does: identify convention-owned paths exempt from marker-based ownership checks
- verify: count(subject="assumed-owned output path matches", equals=1)
- code: `farrier/farrier/outputs.py::is_assumed_owned`

### method: conflicts
- sig: `conflicts(repo: Path, outputs: dict[Path, str], managed: Managed = REPO_MANAGED) -> list[str]`
- does: return sorted output paths held by unowned existing files
- verify: count(subject="unowned output conflicts", equals=1)
- code: `farrier/farrier/outputs.py::conflicts`

### method: refuse_conflicts
- sig: `refuse_conflicts(repo: Path, outputs: dict[Path, str], managed: Managed = REPO_MANAGED) -> None`
- does: abort before mutation when any output conflicts with an unowned file
- raises: `SystemExit` naming every conflicting path
- verify: unchanged(subject="repository after unowned-output refusal")
- code: `farrier/farrier/outputs.py::refuse_conflicts`

### method: remove_targets
- sig: `remove_targets(repo: Path, managed: Managed = REPO_MANAGED) -> None`
- does: delete only marked or convention-owned previous outputs and assumed-owned empty artifacts
- verify: removed(subject="deselected Farrier-owned output")
- code: `farrier/farrier/outputs.py::remove_targets`
- detail: [output cleanup selection](output-cleanup-selection.md)

### method: check_selection
- sig: `check_selection(groups: list[tuple[str, list, set[str]]]) -> None`
- does: reject unmatched literal selections and warn for unmatched globs
- verify: exit_status(code=1)
- code: `farrier/farrier/outputs.py::check_selection`

### method: render_expected
- sig: `render_expected(config: dict[str, Any], repo: Path) -> dict[Path, str]`
- does: resolve configured selections into the expected output set
- verify: count(subject="expected repository outputs", equals=1)
- does: validate selections before rendering outputs
- verify: exit_status(code=1)
- does: render the selected adapters
- verify: count(subject="rendered adapter outputs", equals=1)
- does: render local instructions for configured paths
- verify: count(subject="rendered local instruction outputs", equals=1)
- does: add hook outputs when a manager is configured
- verify: count(subject="configured hook outputs", equals=1)
- code: `farrier/farrier/outputs.py::render_expected`

### method: render_user_expected
- sig: `render_user_expected(config: dict[str, Any], home: Path) -> dict[Path, str]`
- does: render configured user-scope harness selections without repository scaffolding
- verify: absent(subject="repository scaffolding in user-scope output map")
- code: `farrier/farrier/outputs.py::render_user_expected`

### method: selected_hooks
- sig: `selected_hooks(prefix: str, skills) -> list[SkillHook]`
- does: collect hooks declared by selected library skills in selection order
- verify: count(subject="selected skill hooks", equals=1)
- code: `farrier/farrier/outputs.py::selected_hooks`

### method: check_outputs
- sig: `check_outputs(repo: Path, outputs: dict[Path, str], manager: str | None = None, managed: Managed = REPO_MANAGED) -> int`
- does: report missing, changed, extra, and hook-fence drift without writing
- returns: `1` when any drift exists and `0` otherwise
- verify: unchanged(subject="repository after output check")
- code: `farrier/farrier/outputs.py::check_outputs`

### method: ensure_gitignore_entry
- sig: `ensure_gitignore_entry(repo: Path, entry: str) -> bool`
- does: append one exact ignore entry with separation and no duplicate
- verify: count(subject="duplicate gitignore entries", equals=0)
- code: `farrier/farrier/outputs.py::ensure_gitignore_entry`

### method: ensure_agents_gitignore
- sig: `ensure_agents_gitignore(repo: Path) -> bool`
- does: replace superseded `.agents` ignore spellings with the current managed block
- verify: count(subject="managed agents gitignore block", equals=1)
- code: `farrier/farrier/outputs.py::ensure_agents_gitignore`

### method: ensure_makefile_include
- sig: `ensure_makefile_include(repo: Path) -> bool`
- does: append a marked launcher include to an existing root Makefile without replacing its content
- verify: count(subject="generated launcher include blocks", equals=1)
- code: `farrier/farrier/outputs.py::ensure_makefile_include`

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
- code: `farrier/farrier/outputs.py::install_outputs`
