---
type: concept
slug: author-artifact-gates
title: Author artifact gates
---
# Author artifact gates

The Author main machine uses these nodes as its final artifact boundary. Reconciliation compares
planning scope with a committed baseline, integrity delegates graph-reference checking to Ostler,
artifact validation confirms that the queue contains runnable authored work, and the commit node
ships only the paths Author owns. Missing infrastructure is skipped only where the individual gate
explicitly defines that fail-open behavior; actual findings remain blocking results.

- code: `workflows/src/workhorse_workflows/author/main/nodes/artifacts.py::verify_reconcile`
- detail: [author finalize subflow](author-finalize-subflow.md)
- detail: [author shared schemas](author-shared-schemas.md)

## Methods

### verify_reconcile

Compares the current epic seed and story identifiers with the committed baseline so a rerun cannot
silently remove previously committed planning scope.

- sig: `verify_reconcile(logger: logging.Logger, ref: str = "HEAD", repo_dir: str = "") -> VerifyReport`
- does: trims the baseline reference, resolves the launch repository root, and locates the configured epics directory
- verify: count(subject="reconciliation repository resolutions", equals=1)
- does: skips when the baseline cannot be read and the repository is not a git repository
- verify: count(subject="non-git reconciliation skips", equals=1)
- does: skips when the epics directory does not exist
- verify: count(subject="missing epics directory skips", equals=1)
- does: skips when no epic has a committed baseline
- verify: count(subject="baseline-free reconciliation skips", equals=1)
- does: reports every committed seed subsection absent from the current epic as a dropped seed
- verify: count(subject="dropped seed findings", equals=1)
- does: reports every committed story subsection absent from the current epic as a dropped story
- verify: count(subject="dropped story findings", equals=1)
- does: returns a holding report when all baseline epic seed and story identifiers remain present
- verify: count(subject="reconciliation holding reports", equals=1)
- does: returns an error report when any committed seed or story identifier was removed
- verify: count(subject="reconciliation drop reports", equals=1)
- returns: returns `VerifyReport` with `skipped`, `holds`, `errors`, and a reconciliation summary
- verify: count(subject="reconciliation reports", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/nodes/artifacts.py::verify_reconcile`
- tests: `workflows/tests/author/finalize/test_flow.py::test_finalizes_with_one_commit_on_the_current_branch`

### verify_integrity

Runs whole-graph Ostler validation and converts error-severity findings into a blocking report while
allowing an unloadable graph to be explicitly skipped.

- sig: `verify_integrity(logger: logging.Logger, epic: str = "", repo_dir: str = "") -> VerifyReport`
- does: resolves the launch repository root and runs Ostler doctor for the requested epic, or the whole graph when `epic` is blank
- verify: count(subject="whole graph integrity checks", equals=1)
- does: skips when Ostler reports an invalid or unloadable graph
- verify: count(subject="unloadable integrity skips", equals=1)
- does: ignores warning-severity findings when deciding whether integrity holds
- verify: count(subject="integrity warning-only reports", equals=1)
- does: returns a holding report when no error-severity findings exist
- verify: count(subject="integrity holding reports", equals=1)
- does: returns an error report listing each error-severity finding when graph integrity fails
- verify: count(subject="integrity error reports", equals=1)
- returns: returns `VerifyReport` with the doctor summary and either a hold, skip, or formatted errors
- verify: count(subject="integrity reports", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/nodes/artifacts.py::verify_integrity`
- tests: `workflows/tests/author/finalize/test_flow.py::test_finalizes_with_one_commit_on_the_current_branch`
- tests: `workflows/tests/author/finalize/test_flow.py::test_terminal_validation_commits_incomplete_then_fails`

### validate_artifacts

Checks that the planning artifacts left for the coder are loadable, authored, and contain at least
one selectable story.

- sig: `validate_artifacts(logger: logging.Logger, repo_dir: str = "") -> Defects`
- does: loads the todo queue through Ostler, falling back to milestone epics and then all graph epics when earlier sources are empty
- verify: count(subject="artifact queue fallback checks", equals=1)
- does: canonicalizes queued epic names through Ostler and removes duplicate epic entries
- verify: removed(subject="duplicate entries for the same canonical epic")
- verify: count(subject="canonical artifact epic queues", equals=1)
- does: reports an error for every queued epic Ostler cannot load
- verify: count(subject="unloadable artifact epics", equals=1)
- does: reports an error for every queued epic with no stories
- verify: count(subject="storyless artifact epics", equals=1)
- does: reports an error when a queued story document is missing
- verify: count(subject="missing authored story documents", equals=1)
- does: reports an error when a queued story document remains an unauthored scaffold
- verify: count(subject="unauthored story documents", equals=1)
- does: counts authored stories whose status is not done as selectable work
- verify: count(subject="selectable authored stories", equals=1)
- does: reports an error when no selectable story remains and no earlier artifact errors exist
- verify: count(subject="empty selectable artifact queues", equals=1)
- returns: returns `Defects` with `ok` true only when the queue has no errors and at least one selectable story
- verify: count(subject="validated artifact defect reports", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/nodes/artifacts.py::validate_artifacts`
- tests: `workflows/tests/author/test_workflow.py::test_author_nodes_use_milestones_when_todo_is_absent`

### commit_author

Commits the author-owned documentation and Ostler ID registry on the current branch, using a
distinct incomplete message on the final-gate failure edge. A verification scenario invokes the
node in a fixture repository and captures the created commit subject.

- sig: `commit_author(logger: logging.Logger, mode: str = "epic", epic: str = "", bullet: str = "", roadmap: str = "", repo_dir: str = "", docs_dir: str = "docs", id_registry: str = ".agents/ids.json") -> Committed`
- does: resolves the repository root
- verify: count(subject="author commit repository resolutions", equals=1)
- does: returns without committing when no git directory exists
- verify: count(subject="non-git author commits", equals=0)
- does: scopes the commit to existing `docs_dir` and `id_registry` paths, omitting missing scopes
- verify: count(subject="author commit scopes", equals=1)
- does: uses `author: INCOMPLETE — roadmap <roadmap stem>, do not merge` when `mode="incomplete"` has a roadmap
- verify: json_path(path="commit.subject", equals="author: INCOMPLETE — roadmap account-access, do not merge")
- does: uses `author: INCOMPLETE — unwritten stories, do not merge (<epic>)` when `mode="incomplete"` has an epic but no roadmap
- verify: json_path(path="commit.subject", equals="author: INCOMPLETE — unwritten stories, do not merge (accounts)")
- does: uses `author: INCOMPLETE — unwritten stories, do not merge` when `mode="incomplete"` has neither roadmap nor epic
- verify: json_path(path="commit.subject", equals="author: INCOMPLETE — unwritten stories, do not merge")
- does: uses `author: <epic> — <first bullet line>` when `mode="story"` has an epic
- verify: json_path(path="commit.subject", equals="author: accounts — sign in")
- does: uses `author: <canonical epic> — <first bullet line>` when `mode="epic-edit"` has an epic
- verify: json_path(path="commit.subject", equals="author: account-access — define access")
- does: uses `author: roadmap <roadmap stem>` when a non-incomplete commit has a roadmap
- verify: json_path(path="commit.subject", equals="author: roadmap account-access")
- does: uses `author: epic authoring` when no message-specific mode or context is supplied
- verify: json_path(path="commit.subject", equals="author: epic authoring")
- does: commits the selected scopes through the shared commit operation
- verify: persists(subject="author-owned planning documents")
- returns: returns `Committed` with `committed` indicating whether the scoped commit was created
- verify: count(subject="author commit results", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/nodes/artifacts.py::commit_author`
- tests: `workflows/tests/author/finalize/test_flow.py::test_finalizes_with_one_commit_on_the_current_branch`
- tests: `workflows/tests/author/finalize/test_flow.py::test_terminal_validation_commits_incomplete_then_fails`
