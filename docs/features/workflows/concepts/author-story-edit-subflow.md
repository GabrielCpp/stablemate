---
type: concept
slug: author-story-edit-subflow
title: Author story edit subflow
---
# Author story edit subflow

The `story_edit` package is the thin story-scope entry point for Author. It validates one add or
remove request, resolves it to an [edit intent](../edit-intent.md), and hands that intent to the
[author epic edit flow](../flows/author-epic-edit.md). It owns no graph mutation: the epic-edit
subflow performs the sole reconciliation and commit pass. Its deterministic nodes are registered
on one package-local blueprint, which the author composition root imports into its registry.

- code: `workflows/src/workhorse_workflows/author/story_edit/flow.py::StoryEdit`
- code: `workflows/src/workhorse_workflows/author/story_edit/nodes.py::blueprint`
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_add_authors_one_story_and_commits`

## Methods

### blueprint
- sig: `Blueprint("author-story-edit") -> Blueprint`
- does: provides the node-registration target for the story-edit resolver
- returns: returns a blueprint named `author-story-edit`
- verify: json_path(path="$.name", equals="author-story-edit")
- code: `workflows/src/workhorse_workflows/author/story_edit/nodes.py::blueprint`

### setup
- sig: `setup() -> Config`
- does: loads the configured author paths in `story-edit` mode
- does: refuses to start when the configured backlog file is absent
- returns: returns the resolved author configuration to the flow context
- verify: count(subject="story-edit configuration loads", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_edit/flow.py::StoryEdit.setup`

### labels
- sig: `labels() -> dict[str, str]`
- does: labels an add run with its epic and a remove run with its story
- returns: returns labels containing the work id, epic, and reconciliation progress text
- verify: json_path(path="$.progress", equals="reconciling epic scope")
- code: `workflows/src/workhorse_workflows/author/story_edit/flow.py::StoryEdit.labels`

### start
- sig: `start() -> Done`
- does: adopts unnamed backlog bullets before resolving an add request
- does: resolves the requested story operation into an edit intent
- does: hands the intent and operator mode to `EpicEdit`
- returns: returns `Done` containing the epic-edit handoff result
- verify: count(subject="story-edit epic-edit handoffs", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_edit/flow.py::StoryEdit.start`

## Resolution

### resolve_story_intent
- sig: `resolve_story_intent(logger: logging.Logger, action: str, epic: str = "", story: str = "", bullet: str = "", reason: str = "", force: bool = False, repo_dir: str = "") -> EditIntent`
- does: for `add`, strips the epic input before storing it
- consistency: for `add`, rejects a blank epic with `WorkflowFailed`
- verify: json_path(path="exception.type", equals="WorkflowFailed")
- does: for `add`, strips the bullet input before resolving it
- does: for `add`, rejects a blank bullet
- does: for `add`, resolves a backlog id, backlog text, or literal bullet through `resolve_bullet`
- does: for `add`, logs the resolved bullet id with the target epic
- does: for `add`, strips the reason before storing it
- does: for `add`, uses `Add a story for <source_bullet>` when the stripped reason is empty
- does: for `add`, preserves the caller's force flag
- does: for `remove`, rejects an action other than `remove`
- does: for `remove`, strips the story slug before lookup
- does: for `remove`, rejects a blank story slug
- does: for `remove`, lists stories through Ostler using `repo_dir`
- does: for `remove`, selects the row whose slug exactly equals the stripped story slug
- does: for `remove`, rejects a story slug absent from Ostler's story list
- does: for `remove`, reads the selected story's status
- does: for `remove`, rejects a status other than `Not started` when force is false
- does: for `remove`, logs the resolved story slug with its parent epic
- does: for `remove`, strips the reason before storing it
- does: for `remove`, uses `Remove story <story> and reconcile its epic scope` when the stripped reason is empty
- does: for `remove`, preserves the caller's force flag
- returns: for `add`, returns an [edit intent](../edit-intent.md) with kind `add-story`
- returns: for `add`, returns the trimmed epic
- returns: for `add`, returns the resolved bullet id and source text
- returns: for `add`, returns whether the bullet came from the backlog
- returns: for `add`, returns the supplied or generated change reason
- returns: for `remove`, returns an [edit intent](../edit-intent.md) with kind `remove-story`
- returns: for `remove`, returns the selected story's parent epic and slug
- returns: for `remove`, returns the supplied or generated change reason
- returns: for `remove`, returns the force flag
- raises: `WorkflowFailed` when an add request has a blank epic
- raises: `WorkflowFailed` when an add request has a blank bullet
- raises: `WorkflowFailed` when action is neither `add` nor `remove`
- raises: `WorkflowFailed` when a remove request has a blank story slug
- raises: `WorkflowFailed` when the requested story is absent
- raises: `WorkflowFailed` when a started story is removed without force
- does: performs no graph mutation
- verify: count(subject="resolved add-story or remove-story intent", equals=1)
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_add_authors_one_story_and_commits`
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_remove_refuses_a_started_story_without_force`
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_remove_deletes_an_unstarted_story_and_commits`
- code: `workflows/src/workhorse_workflows/author/story_edit/nodes.py::resolve_story_intent`
