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

- code: `workflows/src/workhorse_workflows/coder/shared/story.py::__all__` @7308a4f16d6e
- detail: [Coder shared library](coder-shared-library.md)
- detail: [Coder documentation schemas](coder-docs-schemas.md)
- detail: [Story worktree boundary](story-worktree-boundary.md)

The pipeline treats an empty story handle as a no-work input, but a non-empty handle (an id or a
slug) that resolves to no readable story file as a workflow failure. The documentation root is
included in agent read directories.
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
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::guard_story_file` @7308a4f16d6e

### prepare_story
- sig: `prepare_story(logger, story: str = "", epic: str = "", repo_dir: str = "") -> StoryPaths`
- does: returns blank paths when no story handle is supplied
- verify: json_path(path="$.story_slug", equals="")
- does: resolves the given handle, a minted story id or a slug, through the graph's `find_story` then `story_by_slug`, and takes the epic from the resolved entry rather than scanning the epics tree
- verify: json_path(path="$.story_epic", equals="acme-epic")
- does: refuses a graph-known story whose authored contract is incomplete
- verify: count(subject="unauthored story preparation failures", equals=1)
- does: resolves the story spec directory through Ostler from the resolved story's minted id
- verify: json_path(path="$.spec_dir", equals="docs/stories/acme-story")
- does: returns canonical absolute story, spec, and QA paths
- verify: count(subject="resolved story path results", equals=1)
- does: returns the story slug alongside the resolved paths
- verify: count(subject="resolved story slug results", equals=1)
- does: returns the story epic alongside the resolved paths
- verify: count(subject="resolved story epic results", equals=1)
- does: returns the resolved story's minted id alongside the resolved paths, which resolution guarantees is never empty for a non-blank handle
- verify: count(subject="resolved story id results", equals=1)
- raises: `WorkflowFailed` when the handle resolves to no story, or to a story with no minted id
- verify: count(subject="unresolvable story handle failures", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::prepare_story` @7308a4f16d6e
- detail: [Story paths](../formats/story-paths.md)

### resolve_workspace_dirs
- sig: `resolve_workspace_dirs(logger, repo_dir: str = "", workspace: str = "") -> WorkspaceDirs`
- does: resolves readable workspace repository directories from the workspace file and repository root
- verify: count(subject="resolved workspace directory results", equals=1)
- does: prepends the docs root when it is not already one of the resolved directories
- verify: count(subject="agent read sets containing the docs root", equals=1)
- returns: the ordered directory list for agent turns
- verify: json_path(path="$.dirs", matches="^\[.*\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::resolve_workspace_dirs` @7308a4f16d6e
- detail: [Workflow workspace directories](../formats/workspace-dirs.md)

### workspace_dirs
- sig: `workspace_dirs(flow: Workflow) -> list[str]`
- does: reads the recorded workspace-resolution output instead of resolving directories again
- verify: count(subject="workspace read sets read from setup output", equals=1)
- returns: a copy of the recorded agent-readable directory list
- verify: json_path(path="$.dirs", matches="^\[.*\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::workspace_dirs` @7308a4f16d6e
- detail: [Workflow workspace directories](../formats/workspace-dirs.md)

### stamp_specs
- sig: `stamp_specs(logger, story_id: str = "", repo_dir: str = "") -> SpecsStamped`
- does: leaves the run successful without stamping when no story id or spec directory exists
- verify: count(subject="no-op spec stamping passes", equals=1)
- does: creates each direct markdown spec document's OKF type through Ostler, keyed on the story id, without rewriting an already typed document
- verify: count(subject="typed spec documents after stamping", equals=2)
- raises: `WorkflowFailed` when a direct markdown spec remains untyped after the stamping pass
- verify: count(subject="untyped spec stamping failures", equals=1)
- returns: the number of documents newly stamped in this pass
- verify: json_path(path="$.stamped", matches="^[0-9]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::stamp_specs` @7308a4f16d6e
- detail: [Stamped specs result](../formats/specs-stamped.md)

### prepare_fix_story
- sig: `prepare_fix_story(logger, story: str = "", epic: str = "", repo_dir: str = "") -> StoryPaths`
- does: resolves the fix story of a drained register record with the same paths, authored gate, and identity fields as ordinary story preparation
- verify: count(subject="fix story preparations", equals=1)
- does: records the fix preparation under a distinct node identity so it cannot overwrite the parent story preparation output
- verify: count(subject="distinct fix-story preparation outputs", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::prepare_fix_story` @7308a4f16d6e
- detail: [Story paths](../formats/story-paths.md)
