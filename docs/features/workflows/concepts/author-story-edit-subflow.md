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
- does: for `add`, rejects a blank epic
- does: for `add`, rejects a blank bullet
- does: for `add`, resolves a backlog id, backlog text, or literal bullet into an intent source
- does: for `add`, returns kind `add-story` with the trimmed epic, resolved bullet id, source text, backlog provenance, change reason, and force flag
- does: for `remove`, rejects an action other than `remove` after the add branch
- does: for `remove`, rejects a blank story slug
- does: for `remove`, rejects a story slug absent from Ostler's story list
- does: for `remove`, rejects started work unless `force` is true
- does: for `remove`, returns kind `remove-story` with the story's parent epic, slug, change reason, and force flag
- returns: returns an [edit intent](../edit-intent.md) without mutating the graph
- verify: count(subject="resolved story edit intents", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_edit/nodes.py::resolve_story_intent`
