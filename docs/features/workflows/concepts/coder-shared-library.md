---
type: concept
slug: coder-shared-library
title: Coder shared library
---
# Coder shared library

The Coder flows share this package for the contracts and state transitions that must mean the
same thing in more than one machine. The package exposes only the common blueprint from its
initializer; the individual modules below own the behavior and models they provide.

- code: `workflows/src/workhorse_workflows/coder/shared/__init__.py::__all__`
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::__all__`
- code: `workflows/src/workhorse_workflows/coder/shared/qa_support.py::QA_PLAN_FILE`
- code: `workflows/src/workhorse_workflows/coder/shared/qa_support.py::QA_RUN_LOG`
- detail: [coder queue run scope](../coder-queue-run-scope.md)
- detail: [coder queue base branch](../coder-queue-base-branch.md)
- detail: [coder queue story branch](../coder-queue-story-branch.md)
- detail: [coder queue epic pick](../coder-queue-epic-pick.md)
- detail: [coder queue epic branch](../coder-queue-epic-branch.md)
- detail: [coder queue story pick](../coder-queue-story-pick.md)
- detail: [coder queue epic blocked](../coder-queue-epic-blocked.md)
- detail: [coder queue epic pruned](../coder-queue-epic-pruned.md)
- detail: [coder queue story committed](../coder-queue-story-committed.md)
- detail: [coder queue worktree cleanliness](../coder-queue-worktree-cleanliness.md)
- detail: [coder queue worktree settled](../coder-queue-worktree-settled.md)
- detail: [coder queue story stamped](../coder-queue-story-stamped.md)
- detail: [coder queue replan result](../coder-queue-replan-result.md)
- detail: [coder rendered schema contracts](coder-render-schema-contracts.md)
- detail: [coder fix selection result](../fix-pick.md)
- detail: [coder fix story seed result](../fix-story-seed.md)
- detail: [coder pruned fix result](../fix-pruned.md)
- detail: [coder blocked fix result](../fix-blocked.md)
- detail: [genesis target classification](../genesis-target-classification.md)
- detail: [genesis Git initialization result](../genesis-git-init.md)
- detail: [genesis agents configuration result](../genesis-agents-yml.md)
- detail: [genesis skeleton result](../genesis-skeleton.md)
- detail: [genesis Farrier installation result](../genesis-farrier-install.md)
- detail: [genesis validation report](../genesis-report.md)
- detail: [coder shared dry-run stubs](coder-shared-dry-run-stubs.md)
- detail: [coder shared development helpers](coder-shared-dev.md)
- detail: [coder shared documentation helpers](coder-shared-documentation.md)
- detail: [coder QA run log](../qa-run-log.md)
- detail: [coder dev-fix result](../dev-fix-result.md)
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

The queue module is the main-loop spine. It clears run-scoped ledgers before a fresh run,
selects and branches epics and stories, keeps blocked work unmerged, checks that implementation
work is recorded, and records a passing story only after its implementation commits succeed.
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
- code: `workflows/src/workhorse_workflows/coder/shared/qa_support.py::parse_source_roots`

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
- code: `workflows/src/workhorse_workflows/coder/shared/qa_support.py::assert_records`

### failed_assertions

- sig: `failed_assertions(log_path: Path) -> dict[str, list[str]]`
- does: considers only assertion records whose case-insensitive trimmed `result` is `FAIL`
- verify: json_path(path="$.copy-link", matches="^\\['copy-link-1'\\]$")
- does: ignores failed records without a non-empty trimmed scenario name
- verify: json_path(path="$.", absent=true)
- returns: scenario names mapped to failed assertion ids in log order, using `?` when an id is absent
- verify: json_path(path="$.copy-link", matches="^\\['copy-link-1', '\\?'\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/qa_support.py::failed_assertions`

### scored_run_log

- sig: `scored_run_log(spec_dir: Path) -> Path`
- returns: the scored log path formed as `<spec_dir>/qa/qa-run.ndjson`
- verify: json_path(path="$.path", matches=".*/qa/qa-run\\.ndjson")
- code: `workflows/src/workhorse_workflows/coder/shared/qa_support.py::scored_run_log`

### notes_for

- sig: `notes_for(outcome: QaOutcome, fallback: str) -> str`
- does: selects the first truthy value from outcome data in the order `notes`, `message`, `problems`, `errors`, `healthFindings`
- verify: json_path(path="$.notes", matches=".+")
- does: serializes a selected non-string value as sorted-key JSON
- verify: json_path(path="$.notes", matches="^\\{.*\\}$")
- does: uses the outcome message only when the outcome is not ok and no selected data value exists
- verify: json_path(path="$.notes", matches=".+")
- returns: the supplied fallback when no diagnostic value is available
- verify: json_path(path="$.notes", equals="fallback")
- code: `workflows/src/workhorse_workflows/coder/shared/qa_support.py::notes_for`

### begin_run

- sig: `begin_run(logger: logging.Logger, run_dir: str = "") -> RunScope`
- does: when `run_dir` is supplied, removes the prior run's `blocked-epics.txt`, `qa-skip-stories.txt`, and `epic-branches.txt` ledgers
- returns: the names of removed ledgers, or an empty list when no run directory or stale files exist
- verify: absent(subject="stale per-run queue ledgers after a fresh run begins")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::begin_run`
- tests: `workflows/tests/coder/test_workflow.py::test_a_fresh_run_drops_the_skip_state_a_previous_run_left_in_the_run_dir`

### epics_set_aside

- sig: `epics_set_aside(root: Path, run_dir: str) -> list[str]`
- does: reads the current run's `blocked-epics.txt` ledger relative to the documentation root when `run_dir` is relative
- returns: non-empty ledger lines in file order, or an empty list when the run directory, ledger, or file is unreadable
- verify: count(subject="returned set-aside epics", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::epics_set_aside`

### legacy_queue

- sig: `legacy_queue(root: Path) -> Path`
- does: returns the path to the legacy JSON queue sidecar for backward compatibility with repos and sandboxes that have no doc graph
- returns: the `epics-todo.json` file path beside the ostler-managed `index.md` in the documentation root
- verify: json_path(path="$.path", matches=".*epics-todo\\.json")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::legacy_queue`

The legacy queue is used as a fallback by `select_epic` and `prune_epic` when Ostler is unavailable or cannot return an epic list from the documentation graph. It is not read or maintained by the workflow when Ostler is working — Ostler's queue is authoritative when present.

### init_base

- sig: `init_base(logger: logging.Logger, repo_dir: str = "") -> BaseBranch`
- does: chooses the attached current branch unless it is a `feat/` or `rewrite/` branch
- does: falls back through the repository default branch, local `main`, local `master`, and `main`
- returns: the selected non-empty base branch name
- verify: json_path(path="$.base_branch", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::init_base`
- tests: `workflows/tests/coder/test_workflow.py::test_one_epic_of_one_story_builds_it_prunes_the_queue_and_ends_on_an_empty_queue`

### branch_story

- sig: `branch_story(logger: logging.Logger, story: str = "", docs_path: str = "", spec_dir: str = "", repo_dir: str = "", workspace_file: str = "") -> StoryBranch`
- does: cuts or checks out a branch named exactly for the story slug in the documentation repository
- does: branches each affected workspace repository named by the story plan, excluding the documentation repository when already handled
- does: reuses an existing story branch without resetting its commits
- returns: the base branch, story branch, and names of repositories actually branched
- verify: json_path(path="$.story_branch", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::branch_story`
- tests: `workflows/tests/coder/test_workflow.py::test_story_mode_cuts_its_own_branch_and_ends_at_its_own_pr`

### branch_epic

- sig: `branch_epic(logger: logging.Logger, epic: str = "", base_branch: str = "", run_dir: str = "", repo_dir: str = "") -> EpicBranch`
- does: restores the queue index before changing the epic checkout
- does: creates or checks out `feat/<epic>` when the branch is absent or safely owned by this run
- does: returns to a previously claimed branch without resetting its committed work
- does: merges the current base into a previously set-aside branch when the base advanced cleanly
- does: refuses a branch held by another worktree or containing unclaimed unmerged work
- does: reconciles the epic queue from the base branch when the base contains a valid queue
- raises: `WorkflowFailed` when checkout, safe branch reuse, or base reconciliation cannot proceed without discarding or guessing about work
- returns: the selected epic and its `feat/<epic>` branch name
- verify: unchanged(subject="unclaimed unmerged branch after branch refusal")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::branch_epic`
- tests: `workflows/tests/coder/test_workflow.py::test_a_branch_another_working_tree_holds_is_refused_by_name`

### select_epic

- sig: `select_epic(logger: logging.Logger, docs_path: str = "", run_dir: str = "", repo_dir: str = "") -> EpicPick`
- does: reads the epic queue from Ostler and falls back to `epics-todo.json` when Ostler is unavailable or empty while the sidecar exists
- does: returns the first queued epic not listed in this run's blocked ledger
- does: reports an empty queue as finished and an all-blocked queue as set aside without modifying the queue
- does: leaves the queue unchanged when Ostler cannot read it and no valid legacy sidecar is available
- returns: `has_epic=true` with the selected epic, or `has_epic=false` with a reason
- verify: json_path(path="$.has_epic", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::select_epic`
- tests: `workflows/tests/coder/test_workflow.py::test_one_epic_of_one_story_builds_it_prunes_the_queue_and_ends_on_an_empty_queue`

### flag_epic_blocked

- sig: `flag_epic_blocked(logger: logging.Logger, epic: str = "", run_dir: str = "", detail: str = "") -> EpicBlocked`
- does: records a supplied epic once in `blocked-epics.txt` for the remainder of the current run
- does: leaves the epic in the queue and reports that its branch remains unmerged
- does: reports a missing epic without creating per-run state
- returns: the blocked flag, the comma-joined blocked set, and a reason
- verify: persists(subject="the blocked epic ledger for the current run")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::flag_epic_blocked`
- tests: `workflows/tests/coder/test_workflow.py::test_an_epic_branch_carrying_a_set_aside_epic_declines_to_open_a_pr`

### prune_epic

- sig: `prune_epic(logger: logging.Logger, epic: str = "", todo_path: str = "", repo_dir: str = "") -> EpicPruned`
- does: removes the supplied merged epic from an explicit JSON sidecar when `todo_path` is set
- does: otherwise removes the supplied epic through Ostler, then falls back to the legacy sidecar
- does: treats a missing queue, absent epic, malformed sidecar, or write failure as a non-fatal no-op
- returns: whether an epic entry was removed
- verify: absent(subject="the merged epic in the queue after pruning")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::prune_epic`
- tests: `workflows/tests/coder/test_workflow.py::test_one_epic_of_one_story_builds_it_prunes_the_queue_and_ends_on_an_empty_queue`

### select_story

- sig: `select_story(logger: logging.Logger, epic: str = "", docs_path: str = "", run_dir: str = "", repo_dir: str = "") -> StoryPick`
- does: asks Ostler for the next story report while excluding slugs in the operator-maintained skip set
- does: reports `story` with the story path, spec directory, slug, minted id, and progress when a runnable story exists
- does: reports `done` only when Ostler says every story is complete
- does: reports `blocked` when remaining work is skipped, dependency-blocked, unauthored, or unreadable
- returns: a pessimistic blocked outcome when no epic or no usable Ostler report is available
- verify: json_path(path="$.story_outcome", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::select_story`
- tests: `workflows/tests/coder/test_workflow.py::test_the_story_is_stamped_and_the_next_selection_reads_it_as_done`

The `story_outcome` value is the only merge decision: `story` dispatches implementation,
`done` permits pruning and merge, and `blocked` sends the epic to `flag_epic_blocked` while
leaving its branch and remaining stories unmerged. A missing or failed selection is therefore
also `blocked`, never an implicit `done`.

### check_repos_clean

- sig: `check_repos_clean(logger: logging.Logger, story_slug: str = "", spec_dir: str = "", preexisting: list[str] | None = None, repo_dir: str = "", workspace_file: str = "") -> WorktreeCleanliness`
- does: resolves repositories affected by the story plan, falling back to the repository root when none are named
- does: reports staged, unstaged, and untracked paths
- verify: count(subject="story-owned staged, unstaged, and untracked paths", equals=3)
- does: subtracts untouched pre-existing paths and gate context files from the reported paths
- verify: count(subject="story-owned paths after pre-existing and gate context exclusions", equals=1)
- returns: `clean=true` only when no story-owned uncommitted paths remain, with repository names and dirty paths
- verify: json_path(path="$.clean", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::check_repos_clean`
- tests: `workflows/tests/coder/test_workflow.py::test_one_epic_of_one_story_builds_it_prunes_the_queue_and_ends_on_an_empty_queue`

### stamp_story_passed

- sig: `stamp_story_passed(logger: logging.Logger, epic: str = "", story_slug: str = "", story_path: str = "", repo_dir: str = "") -> StoryStamped`
- does: writes `QA passed` to the story status through the shared status adapter
- does: commits only the status files written by the stamp as a `docs` commit
- returns: whether the status was written and whether it replaced a prior non-default outcome
- verify: persists(subject="the story's QA passed status")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::stamp_story_passed`
- tests: `workflows/tests/coder/test_workflow.py::test_the_story_is_stamped_and_the_next_selection_reads_it_as_done`

### commit_story

- sig: `commit_story(logger: logging.Logger, epic: str = "", story_slug: str = "", spec_dir: str = "", story_path: str = "", repo_dir: str = "", workspace_file: str = "", kind: str = "feat", roots: list[str] | None = None, story_id: str = "") -> StoryCommitted`
- does: commits implementation changes in each affected repository using the requested Conventional Commit kind and repository scope
- does: excludes the documentation host repository unless the story plan explicitly lists it as an implementation target
- does: stamps `QA passed` only after implementation commits succeed
- does: counts only implementation commits in `committed`, not the separate status stamp
- raises: `WorkflowFailed` when git refuses an implementation commit
- returns: whether implementation work committed anywhere and whether the status stamp superseded a prior outcome
- verify: persists(subject="the story implementation commit and separate QA status stamp")
- code: `workflows/src/workhorse_workflows/coder/shared/queue.py::commit_story`
- tests: `workflows/tests/coder/test_workflow.py::test_the_story_and_its_status_stamp_commit_as_conventional_commits`

Implementation commits use the requested Conventional Commit kind and the affected checkout's
package scope. The status stamp is a separate `docs` commit, and its `superseded_outcome` flag
is true only when it replaces a prior non-default, non-passed story outcome.
