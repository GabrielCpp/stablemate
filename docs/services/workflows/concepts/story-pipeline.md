---
type: concept
slug: story-pipeline
title: Coder story pipeline
---
# Coder story pipeline

The shared story pipeline prepares the inputs used by the Coder development, review, docs, QA,
and main flows. Its schema contracts are [Story paths](../formats/story-paths.md),
[Workflow workspace directories](../formats/workspace-dirs.md), [Worktree snapshot](../formats/worktree-snapshot.md),
and [Stamped specs result](../formats/specs-stamped.md). It resolves
a story through Ostler's configured document roots, rejects an unauthored or unreadable story
before an agent turn, records the directories an agent may read, and stamps first-party spec artifacts with their OKF type.

- code: `workflows/src/workhorse_workflows/coder/shared/story.py::__all__` @153899b5f2f0
- detail: [Coder shared library](coder-shared-library.md)
- detail: [Coder documentation schemas](coder-docs-schemas.md)
- detail: [Story worktree boundary](story-worktree-boundary.md)

The pipeline treats an empty story slug as a no-work input, but a non-empty slug that resolves to
no readable story file as a workflow failure. The documentation root is included in agent read
directories.
The fix-story preparation node intentionally shares the preparation behavior under a separate
node identity so its recorded output cannot overwrite the parent story's preparation output.

## Methods

### guard_story_file
- sig: `guard_story_file(logger, story: StoryPaths) -> None`
- does: rejects an empty story path before any agent turn
- verify: count(subject="story-path failures for empty story paths", equals=1)
- does: rejects an empty spec directory before artifact paths are used
- verify: count(subject="story-path failures for empty spec directories", equals=1)
- does: rejects a story path that cannot be read
- verify: count(subject="unreadable story-path failures", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::guard_story_file` @153899b5f2f0

### prepare_story
- sig: `prepare_story(logger, docs_path: str = "", story: str = "", epic: str = "", repo_dir: str = "") -> StoryPaths`
- does: returns blank paths when no story slug is supplied
- verify: json_path(path="$.story_slug", equals="")
- does: discovers the epic by scanning the configured epics tree when no epic is supplied
- verify: json_path(path="$.story_epic", equals="acme-epic")
- does: refuses a graph-known story whose authored contract is incomplete
- verify: count(subject="unauthored story preparation failures", equals=1)
- does: resolves the story spec directory through Ostler and fails the workflow when Ostler rejects the slug
- verify: json_path(path="$.spec_dir", equals="docs/stories/acme-story")
- does: returns canonical absolute story, spec, and QA paths
- verify: count(subject="resolved story path results", equals=1)
- does: returns the story slug alongside the resolved paths
- verify: count(subject="resolved story slug results", equals=1)
- does: returns the story epic alongside the resolved paths
- verify: count(subject="resolved story epic results", equals=1)
- does: returns the minted story id alongside the resolved paths
- verify: count(subject="resolved story id results", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::prepare_story` @153899b5f2f0
- detail: [Story paths](../formats/story-paths.md)

### resolve_workspace_dirs
- sig: `resolve_workspace_dirs(logger, docs_path: str = "", repo_dir: str = "", workspace_file: str = "") -> WorkspaceDirs`
- does: resolves readable workspace repository directories from the workspace file and repository root
- verify: count(subject="resolved workspace directory results", equals=1)
- does: prepends the docs root when it is not already one of the resolved directories
- verify: count(subject="agent read sets containing the docs root", equals=1)
- returns: the ordered directory list for agent turns
- verify: json_path(path="$.dirs", matches="^\[.*\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::resolve_workspace_dirs` @153899b5f2f0
- detail: [Workflow workspace directories](../formats/workspace-dirs.md)

### workspace_dirs
- sig: `workspace_dirs(flow: Workflow) -> list[str]`
- does: reads the recorded workspace-resolution output instead of resolving directories again
- verify: count(subject="workspace read sets read from setup output", equals=1)
- returns: a copy of the recorded agent-readable directory list
- verify: json_path(path="$.dirs", matches="^\[.*\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::workspace_dirs` @153899b5f2f0
- detail: [Workflow workspace directories](../formats/workspace-dirs.md)

### stamp_specs
- sig: `stamp_specs(logger, docs_path: str = "", story_slug: str = "", repo_dir: str = "") -> SpecsStamped`
- does: leaves the run successful without stamping when no story slug or spec directory exists
- verify: count(subject="no-op spec stamping passes", equals=1)
- does: gives each direct markdown spec document an OKF type without rewriting an already typed document
- verify: count(subject="typed spec documents after stamping", equals=2)
- raises: `WorkflowFailed` when a direct markdown spec remains untyped after the stamping pass
- verify: count(subject="untyped spec stamping failures", equals=1)
- returns: the number of documents newly stamped in this pass
- verify: json_path(path="$.stamped", matches="^[0-9]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::stamp_specs` @153899b5f2f0
- detail: [Stamped specs result](../formats/specs-stamped.md)

### prepare_fix_story
- sig: `prepare_fix_story(logger, docs_path: str = "", story: str = "", epic: str = "", repo_dir: str = "") -> StoryPaths`
- does: resolves a backlog fix story with the same paths, authored gate, and identity fields as ordinary story preparation
- verify: count(subject="backlog fix story preparations", equals=1)
- does: records the fix preparation under a distinct node identity so it cannot overwrite the parent story preparation output
- verify: count(subject="distinct fix-story preparation outputs", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::prepare_fix_story` @153899b5f2f0
- detail: [Story paths](../formats/story-paths.md)
