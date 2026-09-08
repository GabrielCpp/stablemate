---
type: concept
slug: author-shared-paths
title: Author shared paths
---
# Author shared paths

The author workflow keeps repository roots and derived artifact locations in one shared module.
The consuming repository is an explicit input; an empty input uses the resolver's documented
walk or current-directory fallback. Document roots are delegated to Ostler, while filenames
invented by the workflow are joined to those resolved directories. The module intentionally
keeps two root policies: survey work discovers a repository marker, while launch work uses the
current directory when no explicit repository was supplied. Git-specific root lookup remains in
`workhorse_workflows.kit.find_repo_root` and is not duplicated here.

- code: `workflows/src/workhorse_workflows/author/shared/paths.py::survey_repo_root`
- tests: `workflows/tests/author/surveyor/test_config.py::test_the_config_derives_every_path_from_survey_dir`
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_config_derives_every_path_under_the_survey_dir`

## Methods

### survey_repo_root
- sig: `survey_repo_root(repo_dir: str | Path = "") -> Path`
- does: returns the resolved explicit repository input when it is non-empty
- verify: count(subject="explicit survey repository roots", equals=1)
- does: when the input is empty, searches the current directory and its ancestors in order
- verify: count(subject="survey repository ancestor searches", equals=1)
- does: returns the first searched directory containing `agents.yml` or a `docs/epics` directory
- verify: count(subject="survey repository root fallback", equals=1)
- does: returns the resolved current directory when no searched directory has either marker
- verify: count(subject="survey repository current-directory fallbacks", equals=1)
- returns: an absolute repository root path
- verify: count(subject="survey repository root results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/paths.py::survey_repo_root`

### launch_repo_root
- sig: `launch_repo_root(repo_dir: str | Path = "") -> Path`
- does: returns the resolved explicit repository input when it is non-empty
- verify: count(subject="explicit launch repository roots", equals=1)
- does: otherwise returns the resolved current directory without inspecting ancestor markers
- verify: count(subject="launch repository current-directory fallback", equals=1)
- returns: an absolute repository root path
- verify: count(subject="launch repository root results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/paths.py::launch_repo_root`

### epics_dir
- sig: `epics_dir(root: str | Path) -> str`
- does: resolves the configured epics directory through Ostler and returns it relative to the repository
- verify: count(subject="resolved author epic directories", equals=1)
- returns: a repository-relative POSIX path
- verify: count(subject="author epic directory results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/paths.py::epics_dir`

### backlog_file
- sig: `backlog_file(root: str | Path) -> str`
- does: resolves the configured backlog path through Ostler
- verify: count(subject="resolved author backlog files", equals=1)
- returns: a repository-relative POSIX path
- verify: count(subject="author backlog path results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/paths.py::backlog_file`

### roadmaps_dir
- sig: `roadmaps_dir(root: str | Path) -> str`
- does: resolves the configured roadmaps directory through Ostler
- verify: count(subject="resolved author roadmap directories", equals=1)
- returns: a repository-relative POSIX path
- verify: count(subject="author roadmap directory results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/paths.py::roadmaps_dir`

### features_dir
- sig: `features_dir(root: str | Path) -> str`
- does: resolves the configured feature-book directory through Ostler
- verify: count(subject="resolved author feature directories", equals=1)
- returns: a repository-relative POSIX path
- verify: count(subject="author feature directory results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/paths.py::features_dir`

### epic_dir
- sig: `epic_dir(root: str | Path, epic: str) -> str`
- does: resolves an epic by its bare slug beneath the configured epics root
- verify: count(subject="resolved author epic paths", equals=1)
- does: matches a bare epic slug to its numbered folder when that folder exists
- verify: count(subject="numbered author epic folder matches", equals=1)
- does: preserves the supplied name as a literal relative join when no numbered epic folder resolves
- verify: count(subject="unresolved author epic path fallbacks", equals=1)
- returns: a repository-relative epic directory path
- verify: count(subject="author epic path results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/paths.py::epic_dir`

### story_dir
- sig: `story_dir(epic_dir_rel: str, slug: str) -> str`
- does: derives a story directory beneath the supplied epic directory using Ostler's story layout
- verify: count(subject="derived author story directories", equals=1)
- returns: the story directory as a POSIX relative path
- verify: count(subject="author story directory results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/paths.py::story_dir`

### author_context
- sig: `author_context(root: str | Path) -> str`
- does: appends `_author-context.md` to the resolved epics directory
- verify: count(subject="author run context paths", equals=1)
- returns: the repository-relative run-wide context path
- verify: count(subject="author run context results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/paths.py::author_context`

### epic_context
- sig: `epic_context(epic_dir_rel: str) -> str`
- does: appends `context.md` to an epic directory after removing trailing separators
- verify: removed(subject="trailing separators from the epic directory path")
- verify: count(subject="author epic context paths", equals=1)
- returns: the epic context path
- verify: count(subject="author epic context results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/paths.py::epic_context`

### story_context
- sig: `story_context(story_dir_rel: str) -> str`
- does: appends `context.md` to a story directory after removing trailing separators
- verify: removed(subject="trailing separators from the supplied story directory path")
- returns: the story context path
- verify: count(subject="author story context results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/paths.py::story_context`
