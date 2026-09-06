---
type: concept
slug: coder-path-resolution
title: Coder path resolution
---
# Coder path resolution

The coder keeps path derivation in one shared module. Repository roots are selected from the
explicit `repo_dir` input or from filesystem markers; document locations are delegated to Ostler;
workflow-created filenames are joined locally. Returned repository paths are relative strings when
they cross a checkpoint or git pathspec boundary, while operator context paths and decision paths
are absolute `Path` values.

The three root resolvers are intentionally not interchangeable. `epics_repo_root` recognizes an
epic/docs checkout, `launch_repo_root` gives the current working directory a first chance for
operator-gate sandboxes, and the plain engine resolver is used by callers outside this module.

## Fields

### AMBIENT
- type: `tuple[str, str, str, str]`
- default: `("repo_dir", "docs_path", "workspace_file", "library_dirs")`
- required: true
- semantics: workflow parameters injected into nodes when a node declares the same parameter and no call-site value was supplied
- verify: json_path(path="$.ambient", matches=".*repo_dir.*")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::AMBIENT`

### OPERATOR_DIR
- type: `str`
- default: `.agents/operator`
- required: true
- semantics: repository-relative directory for operator gate context files when no epic folder is available
- verify: json_path(path="$.operator_dir", equals=".agents/operator")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::OPERATOR_DIR`

## Methods

### epics_repo_root
- sig: `epics_repo_root(repo_dir: str | Path = "") -> Path`
- does: returns the resolved explicit `repo_dir` when it is non-empty
- does: otherwise returns the first current-directory ancestor containing `agents.yml` or a `docs/epics/` directory
- does: returns the resolved current directory when no marker is found
- returns: an absolute repository or documentation-checkout root
- verify: json_path(path="$.result", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::epics_repo_root`

### launch_repo_root
- sig: `launch_repo_root(repo_dir: str | Path = "") -> Path`
- does: returns the resolved explicit `repo_dir` when it is non-empty
- does: returns the current directory before walking parents when it contains `docs/epics/`, `agents.yml`, or `.git`
- does: otherwise returns the first parent containing `agents.yml` or `.git`
- does: returns the current directory when no project marker is found
- returns: an absolute launch root selected with current-directory precedence
- verify: json_path(path="$.result", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::launch_repo_root`

### operator_context_path
- sig: `operator_context_path(root: Path, gate: str, epic: str = "") -> Path`
- does: resolves a named epic through Ostler when `epic` is supplied
- does: returns `<epic-dir>/<gate>-context.md` when the resolved epic directory exists
- does: otherwise returns `<root>/.agents/operator/<gate>-context.<epic>.md` for a named epic
- does: returns `<root>/.agents/operator/<gate>-context.md` when no epic is supplied
- returns: an absolute operator question file path
- verify: json_path(path="$.result", matches=".*-context.*\\.md")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::operator_context_path`
- tests: `workflows/tests/coder/shared/test_paths.py::test_a_gate_with_no_epic_folder_writes_under_the_operator_dir`
- tests: `workflows/tests/coder/shared/test_paths.py::test_an_epic_that_has_a_folder_still_gets_its_questions_next_to_it`

### _rel
- sig: `_rel(root: Path, target: Path) -> str`
- does: returns the target as a POSIX path relative to the resolved root when the target is inside that root
- does: returns the target as an absolute POSIX path when it is outside the root
- returns: a repository-relative or absolute POSIX path string
- verify: json_path(path="$.result", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::_rel`

### epics_dir
- sig: `epics_dir(root: Path, configured: str = "") -> str`
- does: returns the trimmed configured epics directory after removing trailing slashes when configured is non-empty
- does: otherwise resolves the epics root through Ostler and returns its repository-relative POSIX path
- returns: the repository-relative epics directory
- verify: json_path(path="$.result", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::epics_dir`

### backlog_file
- sig: `backlog_file(root: Path, configured: str = "") -> str`
- does: returns the trimmed configured backlog path when configured is non-empty
- does: otherwise resolves the backlog path through Ostler and returns its repository-relative POSIX path
- returns: the repository-relative backlog filename
- verify: json_path(path="$.result", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::backlog_file`
- tests: `workflows/tests/coder/shared/test_paths.py::test_decisions_land_with_the_documents_not_beside_the_service_directories`

### epic_dir_rel
- sig: `epic_dir_rel(root: Path, epic: str, configured: str = "") -> str`
- does: selects the configured epics root when supplied, otherwise the Ostler epics root
- does: resolves the epic beneath that root using Ostler's numbered-or-slug directory rule
- returns: the resolved epic directory as a repository-relative POSIX path
- verify: json_path(path="$.result", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::epic_dir_rel`

### features_dir
- sig: `features_dir(root: Path, configured: str = "") -> str`
- does: returns the trimmed configured feature-book directory when configured is non-empty
- does: otherwise resolves the feature-book root through Ostler and returns its repository-relative POSIX path
- returns: the repository-relative feature-book directory
- verify: json_path(path="$.result", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::features_dir`

### epics_index
- sig: `epics_index(root: Path) -> str`
- does: resolves the Ostler epics index file beneath the configured epics root
- returns: the epics index as a repository-relative POSIX path for git operations
- verify: json_path(path="$.result", matches=".*index.*")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::epics_index`

### epic_dir
- sig: `epic_dir(root: Path, epic: str) -> Path`
- does: resolves an epic by number or bare slug through Ostler
- returns: the absolute epic directory
- verify: json_path(path="$.result", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::epic_dir`

### story_md
- sig: `story_md(root: Path, epic: str, slug: str) -> Path`
- does: resolves the story directory for `slug` inside `epic` through Ostler
- returns: the absolute `story.md` path inside the resolved story directory
- verify: json_path(path="$.result", matches=".*story\\.md")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::story_md`

### story_context_path
- sig: `story_context_path(story_path: str, repo_dir: str | Path = "") -> Path`
- does: returns `context.md` beside the supplied story path when `story_path` is non-empty
- does: otherwise returns `context.md` beneath the launch root selected from `repo_dir` and the current directory
- returns: the absolute per-story or standalone operator context path
- verify: json_path(path="$.result", matches=".*context\\.md")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::story_context_path`

### decisions_dir
- sig: `decisions_dir(docs_root: Path) -> Path`
- does: resolves the backlog path beneath `docs_root` through Ostler
- returns: the absolute `decisions` directory beside the resolved backlog
- verify: json_path(path="$.result", matches=".*decisions")
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::decisions_dir`
- tests: `workflows/tests/coder/shared/test_paths.py::test_decisions_land_with_the_documents_not_beside_the_service_directories`

### is_gate_context
- sig: `is_gate_context(path: str | Path) -> bool`
- does: returns false for non-markdown paths
- does: returns true for `context.md`
- does: returns true for markdown names whose stem ends in `-context`, including an optional epic suffix
- returns: whether the path name matches the operator-gate context naming convention
- verify: json_path(path="$.result", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/paths.py::is_gate_context`
- tests: `workflows/tests/coder/shared/test_paths.py::test_the_operator_dir_files_are_still_excused_from_the_dirty_check`
