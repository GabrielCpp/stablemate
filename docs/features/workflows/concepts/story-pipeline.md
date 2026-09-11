---
type: concept
slug: story-pipeline
title: Coder story pipeline
---
# Coder story pipeline

The shared story pipeline prepares the inputs used by the Coder development, review, docs, QA,
and main flows. Its schema contracts are [Story paths](../story-paths.md),
[Workflow workspace directories](../workspace-dirs.md), [Worktree snapshot](../worktree-snapshot.md),
[Plan scrub result](../plan-scrub.md), and [Stamped specs result](../specs-stamped.md). It resolves
a story through Ostler's configured document roots, rejects an unauthored or unreadable story
before an agent turn, records the directories an agent may read, protects code repositories from
planning mutations, and stamps first-party spec artifacts with their OKF type.

- code: `workflows/src/workhorse_workflows/coder/shared/story.py::__all__`
- detail: [Coder shared library](coder-shared-library.md)
- detail: [Coder documentation schemas](coder-docs-schemas.md)
- detail: [Story worktree boundary](story-worktree-boundary.md)

The pipeline treats an empty story slug as a no-work input, but a non-empty slug that resolves to
no readable story file as a workflow failure. The documentation root is included in agent read
directories, while the repository containing plan artifacts is excluded from clean-tree scrubbing.
The fix-story preparation node intentionally shares the preparation behavior under a separate
node identity so its recorded output cannot overwrite the parent story's preparation output.

## Methods

### guard_story_file
- sig: `guard_story_file(story: StoryPaths) -> None`
- does: rejects an empty story path before any agent turn
- verify: count(subject="story-path failures for empty story paths", equals=1)
- does: rejects an empty spec directory before artifact paths are used
- verify: count(subject="story-path failures for empty spec directories", equals=1)
- does: rejects a story path that cannot be read
- verify: count(subject="unreadable story-path failures", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::guard_story_file`

### prepare_story
- sig: `prepare_story(logger, docs_path: str = "", story: str = "", epic: str = "", repo_dir: str = "") -> StoryPaths`
- does: returns blank paths when no story slug is supplied
- verify: json_path(path="$.story_slug", equals="")
- does: discovers the epic by scanning the configured epics tree when no epic is supplied
- verify: json_path(path="$.story_epic", matches=".+")
- does: refuses a graph-known story whose authored contract is incomplete
- verify: count(subject="unauthored story preparation failures", equals=1)
- does: resolves the story spec directory through Ostler, falling back to the configured story layout when necessary
- verify: json_path(path="$.spec_dir", matches=".+")
- does: returns canonical absolute story, spec, and QA paths
- verify: count(subject="resolved story path results", equals=1)
- does: returns the story slug alongside the resolved paths
- verify: count(subject="resolved story slug results", equals=1)
- does: returns the story epic alongside the resolved paths
- verify: count(subject="resolved story epic results", equals=1)
- does: returns the minted story id alongside the resolved paths
- verify: count(subject="resolved story id results", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::prepare_story`
- detail: [Story paths](../story-paths.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_plans_stamps_branches_and_implements_every_layer`

### resolve_workspace_dirs
- sig: `resolve_workspace_dirs(logger, docs_path: str = "", repo_dir: str = "", workspace_file: str = "") -> WorkspaceDirs`
- does: resolves readable workspace repository directories from the workspace file and repository root
- verify: count(subject="resolved workspace directory results", equals=1)
- does: prepends the docs root when it is not already one of the resolved directories
- verify: count(subject="agent read sets containing the docs root", equals=1)
- returns: the ordered directory list for agent turns
- verify: json_path(path="$.dirs", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::resolve_workspace_dirs`
- detail: [Workflow workspace directories](../workspace-dirs.md)

### workspace_dirs
- sig: `workspace_dirs(flow: Workflow) -> list[str]`
- does: reads the recorded workspace-resolution output instead of resolving directories again
- verify: count(subject="workspace read sets read from setup output", equals=1)
- returns: a copy of the recorded agent-readable directory list
- verify: json_path(path="$.dirs", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::workspace_dirs`
- detail: [Workflow workspace directories](../workspace-dirs.md)

### snapshot_worktrees
- sig: `snapshot_worktrees(logger, docs_path: str = "", repo_dir: str = "", workspace_file: str = "") -> WorktreeSnapshot`
- does: records porcelain status for each code repository before a planning turn
- verify: count(subject="pre-plan code worktree snapshots", equals=1)
- does: excludes the resolved documentation root from the snapshot
- verify: absent(subject="documentation root in the code worktree snapshot")
- does: omits repositories whose status cannot be read so scrubbing will skip them
- verify: count(subject="unreadable repositories omitted from snapshots", equals=1)
- returns: status text keyed by absolute repository path
- verify: json_path(path="$.status", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::snapshot_worktrees`
- detail: [Worktree snapshot](../worktree-snapshot.md)
- tests: `workflows/tests/coder/shared/test_clean_tree.py::test_the_snapshot_covers_the_code_repos_and_not_the_docs_root`

### scrub_plan_mutations
- sig: `scrub_plan_mutations(logger, before: dict[str, str] | None = None, docs_path: str = "", repo_dir: str = "", workspace_file: str = "") -> PlanScrub`
- does: restores tracked paths that became dirty in code repositories during the planning turn
- verify: unchanged(subject="tracked code files changed by the plan turn")
- does: deletes untracked files and directories that appeared in code repositories during the planning turn
- verify: removed(subject="untracked plan-turn code artifacts")
- does: preserves paths already dirty in the pre-plan snapshot
- verify: unchanged(subject="pre-existing operator edits")
- does: leaves documentation-repository plan artifacts untouched
- verify: visible(locator="docs plan artifact", text="Plan")
- returns: porcelain and discarded-diff details keyed by affected repository path
- verify: json_path(path="$.reverted", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::scrub_plan_mutations`
- detail: [Plan scrub result](../plan-scrub.md)
- tests: `workflows/tests/coder/shared/test_clean_tree.py::test_the_scrub_reverts_what_the_turn_wrote_and_only_that`
- tests: `workflows/tests/coder/shared/test_clean_tree.py::test_a_turn_that_kept_to_reading_scrubs_nothing`

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
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::stamp_specs`
- detail: [Stamped specs result](../specs-stamped.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_plans_stamps_branches_and_implements_every_layer`

### prepare_fix_story
- sig: `prepare_fix_story(logger, docs_path: str = "", story: str = "", epic: str = "", repo_dir: str = "") -> StoryPaths`
- does: resolves a backlog fix story with the same paths, authored gate, and identity fields as ordinary story preparation
- verify: count(subject="backlog fix story preparations", equals=1)
- does: records the fix preparation under a distinct node identity so it cannot overwrite the parent story preparation output
- verify: count(subject="distinct fix-story preparation outputs", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/story.py::prepare_fix_story`
- detail: [Story paths](../story-paths.md)
