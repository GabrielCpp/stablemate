---
type: concept
slug: coder-shared-library
title: Coder shared library
---
# Coder shared library

The Coder flows share this package for the contracts and state transitions that must mean the
same thing in more than one machine. The package exposes only the common blueprint from its
initializer; the individual modules below own the behavior and models they provide.

- code: `workflows/src/workhorse_workflows/coder/shared/__init__.py::__all__` @e517b81d10c2
- code: `workflows/src/workhorse_workflows/coder/shared/branches.py::__all__` @dc548bba5338
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::__all__` @8e86702bf089
- code: `workflows/src/workhorse_workflows/coder/shared/story_commit.py::__all__` @3dcdcf998a84
- code: `workflows/src/workhorse_workflows/kit/qa/support.py::QA_PLAN_FILE` @df9c5dcbeacb
- code: `workflows/src/workhorse_workflows/kit/qa/support.py::QA_RUN_LOG` @df9c5dcbeacb
- detail: [coder queue run scope](../formats/coder-queue-run-scope.md)
- detail: [coder queue run branch](../formats/coder-queue-run-branch.md)
- detail: [coder queue epic pruned](../formats/coder-queue-epic-pruned.md)
- detail: [coder queue story committed](../formats/coder-queue-story-committed.md)
- detail: [coder queue worktree cleanliness](../formats/coder-queue-worktree-cleanliness.md)
- detail: [coder queue story stamped](../formats/coder-queue-story-stamped.md)
- detail: [coder queue replan result](../formats/coder-queue-replan-result.md)
- detail: [coder rendered schema contracts](coder-render-schema-contracts.md)
- detail: [coder fix selection result](../formats/fix-pick.md)
- detail: [coder fix story seed result](../formats/fix-story-seed.md)
- detail: [coder pruned fix result](../formats/fix-pruned.md)
- detail: [genesis target classification](../formats/genesis-target-classification.md)
- detail: [genesis Git initialization result](../formats/genesis-git-init.md)
- detail: [genesis agents configuration result](../formats/genesis-agents-yml.md)
- detail: [genesis skeleton result](../formats/genesis-skeleton.md)
- detail: [genesis Farrier installation result](../formats/genesis-farrier-install.md)
- detail: [genesis validation report](../formats/genesis-report.md)
- detail: [coder shared dry-run stubs](coder-shared-dry-run-stubs.md)
- detail: [coder shared development helpers](coder-shared-dev.md)
- detail: [coder shared documentation helpers](coder-shared-documentation.md)
- detail: [coder QA run log](../formats/qa-run-log.md)
- detail: [story status persistence](story-status.md)
- detail: [coder conversation lifecycle](coder-conversation.md)
- detail: [coder schemas exports](coder-schemas-exports.md)
- detail: [coder shared commit messages](coder-shared-commit-messages.md)
- detail: [coder shared scenarios](coder-shared-scenarios.md)

`blueprint` is the single node-registration namespace. `paths` derives repository, document,
story, operator-gate, and decision paths from explicit workflow inputs and Ostler's configured
roots. `schemas` supplies agent reply and node-result models, while `stubs` supplies dry-run
values with the same result shapes. `commits` and `worktree` provide shared commit-message and
working-tree boundaries.

The registration object is specified in [coder shared blueprint](coder-shared-blueprint.md).

The path derivation contract is documented in [Coder path resolution](coder-path-resolution.md).

The shared node modules are grouped by responsibility: `contract` validates service roots;
`story` resolves stories and workspaces, protects code trees during planning, and stamps spec
documents; `story_status` reads and writes story outcomes; `queue` selects and records epic and
story work; `backlog` files and drains deferred fixes; `dev` runs implementation gates; `ci`
handles CI outcomes; `docs` and `okf` build documentation and obligation context; `review` and
`resolution` support review and operator decisions; `escalation` writes human-gate context;
`failure` normalizes gate failures; `qa_support` parses QA run logs; `scenarios` parses QA
scenarios; and `conversation` tracks turn budgets. `roles` resolves prompt envelopes and
replacement bodies.

The QA support module owns the two artifact names used by the QA gates: `qa_plan.py` is the
scenario plan relative to a story specification directory, and `qa-run.ndjson` is the assertion
log relative to a scored or scenario-specific QA output directory. Its parsers retain complete
assertion dictionaries so later gates can inspect fields beyond the keys used for routing.

Prompt envelope and replacement-body resolution is documented in [coder prompt role resolution](coder-prompt-role-resolution.md).

Each listed module is a separate bounded source contract. The next crawl pass should document
its public functions, classes, and schema members, then connect their results to the flows that
consume them. No shared module imports a Coder flow or the workflow composition root.

The queue module is the main-loop spine. It clears the worklist and answer log a previous run
left behind, resolves a launch into the stories the run works, and prunes a merged epic from the
queue. The branch and story-commit modules cut the run branch, check that implementation work is
recorded, and record a passing story only after its implementation commits succeed.
Its result models are defined by the adjacent [queue result schemas](../../../../workflows/src/workhorse_workflows/coder/shared/schemas/queue.py)
module; the queue operations return those models rather than printing or exiting.

The result models are separate contracts because each node exposes a different queue decision or
record. Their fields and pessimistic defaults are documented by the linked format nodes; all are
permissive result models that ignore unknown keys and drop null values before applying defaults.

## Methods

### parse_source_roots

- sig: `parse_source_roots(source_roots: list[str]) -> dict[str, list[str]]`
- does: accepts only string entries containing the first `=` separator
- verify: count(subject="source-root entries accepted after parsing", equals=1)
- does: groups the trimmed right-hand paths under each trimmed surface name, preserving input order
- verify: json_path(path="$.api[0]", equals="src/api")
- returns: a surface-to-path-list mapping, with malformed entries ignored
- verify: json_path(path="$.unknown", absent=true)
- code: `workflows/src/workhorse_workflows/kit/qa/support.py::parse_source_roots` @df9c5dcbeacb

### assert_records

- sig: `assert_records(log_path: Path) -> list[dict[str, Any]]`
- does: returns an empty list when the log path is not a regular file
- verify: count(subject="assert records from a missing QA log", equals=0)
- does: reads the NDJSON log line by line and skips malformed JSON lines
- verify: count(subject="assert records retained after a malformed line", equals=1)
- does: retains only dictionary records whose `kind` is exactly `assert`, in file order
- verify: json_path(path="$.kind", equals="assert")
- returns: the retained assertion dictionaries without normalizing or dropping their other keys
- verify: json_path(path="$.id", equals="copy-link-1")
- code: `workflows/src/workhorse_workflows/kit/qa/support.py::assert_records` @df9c5dcbeacb

### failed_assertions

- sig: `failed_assertions(log_path: Path) -> dict[str, list[str]]`
- does: considers only assertion records whose case-insensitive trimmed `result` is `FAIL`
- verify: json_path(path="$.copy-link", matches="^\\[\"copy-link-1\"\\]$")
- does: ignores failed records without a non-empty trimmed scenario name
- verify: json_path(path="$.blank-scenario", absent=true)
- returns: scenario names mapped to failed assertion ids in log order, using `?` when an id is absent
- verify: json_path(path="$.copy-link", matches="^\\[\"copy-link-1\", \"\\?\"\\]$")
- code: `workflows/src/workhorse_workflows/kit/qa/support.py::failed_assertions` @df9c5dcbeacb

### scored_run_log

- sig: `scored_run_log(spec_dir: Path) -> Path`
- returns: the scored log path formed as `<spec_dir>/qa/qa-run.ndjson`
- verify: json_path(path="$.path", matches=".*/qa/qa-run\\.ndjson")
- code: `workflows/src/workhorse_workflows/kit/qa/support.py::scored_run_log` @df9c5dcbeacb

### notes_for

- sig: `notes_for(outcome: QaOutcome, fallback: str) -> str`
- does: selects the first truthy value from outcome data in the order `notes`, `message`, `problems`, `errors`, `healthFindings`
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- does: serializes a selected non-string value as sorted-key JSON
- verify: json_path(path="$.notes", matches="^\\{.*\\}$")
- does: uses the outcome message only when the outcome is not ok and no selected data value exists
- returns: the supplied fallback when no diagnostic value is available
- verify: json_path(path="$.notes", equals="fallback")
- code: `workflows/src/workhorse_workflows/kit/qa/support.py::notes_for` @df9c5dcbeacb

### begin_run

- sig: `begin_run(logger: logging.Logger, run_dir: str = "") -> RunScope`
- does: when `run_dir` is supplied, removes the prior run's `worklist.json` worklist and `answers.md` answer log
- returns: the names of removed files, or an empty list when no run directory or stale files exist
- verify: absent(subject="stale per-run files after a fresh run begins")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::begin_run` @8e86702bf089
- tests: `workflows/tests/coder/test_workflow.py::test_a_fresh_run_drops_the_worklist_and_answers_a_previous_run_left_in_the_run_dir`

### legacy_queue

- sig: `legacy_queue(root: Path) -> Path`
- does: returns the path to the legacy JSON queue sidecar for backward compatibility with repos and sandboxes that have no doc graph
- returns: the `epics-todo.json` file path beside the ostler-managed `index.md` in the documentation root
- verify: json_path(path="$.path", matches=".*epics-todo\\.json")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::legacy_queue` @8e86702bf089

The legacy queue is used as a fallback by `resolve_launch` and `prune_epic` when Ostler is unavailable or cannot return an epic list from the documentation graph. It is not read or maintained by the workflow when Ostler is working — Ostler's queue is authoritative when present.

### epic_branch

- sig: `epic_branch(epic: str) -> str`
- does: prefixes a non-empty epic identifier with `feat/`
- does: returns an empty string when the epic identifier is empty
- returns: the full branch ref used for an epic pull request
- verify: json_path(path="$", equals="feat/EPIC-1")
- code: `workflows/src/workhorse_workflows/coder/shared/branches.py::epic_branch` @dc548bba5338

### epic_of_branch

- sig: `epic_of_branch(branch: str) -> str`
- does: removes the `feat/` prefix when the branch carries that prefix
- does: leaves branches without the `feat/` prefix unchanged
- returns: the bare epic identifier represented by the branch ref
- verify: json_path(path="$", equals="EPIC-1")
- code: `workflows/src/workhorse_workflows/coder/shared/branches.py::epic_of_branch` @dc548bba5338

### cut_run_branch

- sig: `cut_run_branch(logger: logging.Logger, name: str = "", docs_path: str = "", repo_dir: str = "") -> RunBranch`
- does: reads the base as the docs repository's active branch, or its trunk when that branch is a `feat/` or `rewrite/` branch
- does: creates or checks out `feat/<name>` in the docs repository without resetting its commits
- raises: `WorkflowFailed` when the docs root is not a git repository
- returns: the base branch and the `feat/<name>` run branch
- verify: json_path(path="$.branch", equals="feat/EPIC-1")
- code: `workflows/src/workhorse_workflows/coder/shared/branches.py::cut_run_branch` @dc548bba5338
- tests: `workflows/tests/coder/test_workflow.py::test_the_run_branch_is_named_for_what_the_run_was_launched_on`

### branch_code_repos

- sig: `branch_code_repos(logger: logging.Logger, spec_dir: str = "", branch: str = "", docs_path: str = "", repo_dir: str = "", workspace_file: str = "", plan: dict[str, Any] | None = None) -> BranchOutcome`
- does: derives the affected repositories from the plan
- does: uses the documentation repository branch when no branch is supplied, or `main` when that root is not a git repository
- does: creates or checks out the requested branch in each affected code repository
- does: leaves repositories already on the requested branch unchanged and skips non-git repositories
- returns: names of repositories branched and already on the branch
- verify: count(subject="run branch dispatch", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/branches.py::branch_code_repos` @dc548bba5338

### prune_epic

- sig: `prune_epic(logger: logging.Logger, epic: str = "", todo_path: str = "", repo_dir: str = "") -> EpicPruned`
- does: removes the supplied merged epic from an explicit JSON sidecar when `todo_path` is set
- does: otherwise removes the supplied epic through Ostler, then falls back to the legacy sidecar
- does: commits the changed queue file on the current branch after a removal
- does: treats a missing epic name, missing queue, absent epic, malformed sidecar, or write failure as a non-fatal no-op
- returns: whether an epic entry was removed
- verify: absent(subject="the merged epic in the queue after pruning")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::prune_epic` @8e86702bf089
- tests: `workflows/tests/coder/test_workflow.py::test_one_epic_of_one_story_builds_it_prunes_the_queue_and_ends_on_an_empty_queue`

### resolve_launch

- sig: `resolve_launch(logger: logging.Logger, docs_path: str = "", epic: str = "all", story: str = "", repo_dir: str = "") -> LaunchSet`
- does: returns the one named story with its slug, minted id and epic when `story` is set
- verify: json_path(path="$.mode", equals="story")
- raises: `WorkflowFailed` when the book holds no story of that name
- does: reads the epics queue from Ostler and falls back to `epics-todo.json` when `epic` is `all`
- verify: json_path(path="$.mode", equals="epic")
- does: lists the open stories of each launched epic in queue order
- verify: count(subject="launched open stories", equals=2)
- raises: `WorkflowFailed` when the launch names both a story and an epic
- raises: `WorkflowFailed` when a launched story depends on a story the launch does not include
- raises: `WorkflowFailed` when the epics queue cannot be read
- returns: the launch mode and every story the run works, in the order it works them
- verify: json_path(path="$.entries[0].slug", equals="login-form")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::resolve_launch` @8e86702bf089

### check_repos_clean

- sig: `check_repos_clean(logger: logging.Logger, story_slug: str = "", spec_dir: str = "", preexisting: list[str] | None = None, repo_dir: str = "", workspace_file: str = "") -> WorktreeCleanliness`
- does: resolves repositories affected by the story plan, falling back to the repository root when none are named
- does: reports staged, unstaged, and untracked paths
- verify: count(subject="story-owned staged, unstaged, and untracked paths", equals=3)
- does: subtracts untouched pre-existing paths and gate context files from the reported paths
- verify: count(subject="story-owned paths after pre-existing and gate context exclusions", equals=1)
- returns: `clean=true` only when no story-owned uncommitted paths remain, with repository names and dirty paths
- verify: json_path(path="$.clean", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/story_commit.py::check_repos_clean` @3dcdcf998a84
- tests: `workflows/tests/coder/test_workflow.py::test_one_epic_of_one_story_builds_it_prunes_the_queue_and_ends_on_an_empty_queue`

### stamp_story_passed

- sig: `stamp_story_passed(logger: logging.Logger, epic: str = "", story_slug: str = "", story_path: str = "", repo_dir: str = "") -> StoryStamped`
- does: writes `QA passed` to the story status through the shared status adapter
- does: commits only the status files written by the stamp as a `docs` commit
- returns: whether the status was written and whether it replaced a prior non-default outcome
- verify: persists(subject="the story's QA passed status")
- code: `workflows/src/workhorse_workflows/coder/shared/story_commit.py::stamp_story_passed` @3dcdcf998a84
- tests: `workflows/tests/coder/test_workflow.py::test_the_story_is_stamped_and_the_next_selection_reads_it_as_done`

### commit_plan_record

- sig: `commit_plan_record(logger: logging.Logger, epic: str = "", story_slug: str = "", spec_dir: str = "", repo_dir: str = "") -> StoryCommitted`
- does: commits the story's spec directory in the docs repository as a `docs` commit named `record the plan of <slug>`
- verify: persists(subject="the committed plan record")
- does: skips the commit and reports nothing committed when the spec directory is empty or lies outside the repository
- verify: json_path(path="$.committed", equals=false)
- does: commits without running the repository's hooks
- verify: count(subject="plan record commits", equals=1)
- returns: whether the plan record was committed
- verify: json_path(path="$.committed", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/story_commit.py::commit_plan_record` @3dcdcf998a84

### commit_story

- sig: `commit_story(logger: logging.Logger, epic: str = "", story_slug: str = "", spec_dir: str = "", story_path: str = "", repo_dir: str = "", workspace_file: str = "", kind: str = "feat", roots: list[str] | None = None, story_id: str = "") -> StoryCommitted`
- does: commits implementation changes in each affected repository using the requested Conventional Commit kind and repository scope
- does: excludes the documentation host repository unless the story plan explicitly lists it as an implementation target
- does: renders the agent files of each repository before committing in it, and logs a warning when that render fails
- does: stamps `QA passed` only after implementation commits succeed
- does: counts only implementation commits in `committed`, not the separate status stamp
- raises: `WorkflowFailed` when git refuses an implementation commit
- returns: whether implementation work committed anywhere and whether the status stamp superseded a prior outcome
- verify: persists(subject="the story implementation commit and separate QA status stamp")
- code: `workflows/src/workhorse_workflows/coder/shared/story_commit.py::commit_story` @3dcdcf998a84
- tests: `workflows/tests/coder/test_workflow.py::test_the_story_and_its_status_stamp_commit_as_conventional_commits`

Implementation commits use the requested Conventional Commit kind and the affected checkout's
package scope. The status stamp is a separate `docs` commit, and its `superseded_outcome` flag
is true only when it replaces a prior non-default, non-passed story outcome.
