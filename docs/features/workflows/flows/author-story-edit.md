---
type: flow
slug: author-story-edit
title: Author story edit
---
# Author story edit

- The [workhorse-author run command](../workhorse-author.md#run) selects this flow. It validates a
  story-level request, then hands a typed intent to the [author epic edit flow](author-epic-edit.md)
  for the only mutation pass. The [author workflow composition root](../concepts/author-workflow-composition-root.md)
  registers the flow.
- The [author story edit subflow](../concepts/author-story-edit-subflow.md) owns the named machine
  and its `author-story-edit` deterministic-node blueprint; the [edit intent](../edit-intent.md)
  is the handoff format.

- start: an operator invokes `workhorse-author run story-edit` with an `action` of `add` or `remove`
- start: an add request supplies an existing epic and a non-empty bullet reference
- start: a remove request supplies a non-empty existing story slug
- start: a remove request for work whose status is not `Not started` supplies `force: true`
- start: a plan that removes a story other than the requested story supplies `force: true`
- start: a plan that removes a seed not covered by the requested story supplies `force: true`
- start: a plan that removes frozen scope has been unfrozen before execution
- steps:
  - [setup](#setup)
  - [resolve the story intent](#resolve-the-story-intent)
  - [reconcile the parent epic](author-epic-edit.md)
  - [validate and commit](author-epic-edit.md#validate-coverage-and-commit)
- end: an add operation leaves the requested story covering its resolved source item
- end: a remove operation leaves the requested story absent
- end: the parent epic narrative and resulting story graph agree
- end: backlog ownership and milestone references agree with the resulting graph
- end: the whole documentation graph passes integrity before the edit is committed
- verify: created(subject="the requested story under its parent epic")
- verify: removed(subject="the requested story")
- verify: unchanged(subject="the remaining authored story")
- verify: removed(subject="the now-empty epic under the configured epics root")
- verify: exit_status(code=0)
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_add_authors_one_story_and_commits`
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_remove_reconciles_remaining_epic_scope_and_journey`
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_remove_deletes_an_unstarted_story_and_commits`
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_follows_the_configured_epics_root`
- code: `workflows/src/workhorse_workflows/author/story_edit/flow.py::StoryEdit.setup`
- code: `workflows/src/workhorse_workflows/author/story_edit/flow.py::StoryEdit.start`
- code: `workflows/src/workhorse_workflows/author/story_edit/nodes.py::resolve_story_intent`
- detail: [workhorse-author run command](../workhorse-author.md#run)

## Phase Details

### Setup
`StoryEdit.setup` resolves the repository root, backlog, epics root, and feature-book path through
the configured document roots. In `story-edit` mode it refuses to start when the resolved backlog
file is absent.

- code: `workflows/src/workhorse_workflows/author/story_edit/flow.py::StoryEdit.setup`
- code: `workflows/src/workhorse_workflows/author/main/nodes/config.py::load_config`

### Resolve the story intent
For an add, the flow first adopts every unnamed backlog bullet through
`intake.py::adopt_backlog`. The node resolves the consuming repository with the supplied
`repo_dir`, calls Ostler's backlog adoption operation, logs its result message when adoption
succeeds, and returns that result. A failed adoption raises `WorkflowFailed` with Ostler's
failure message, so intent resolution does not run against an unnumbered or partially adopted
worklist. After adoption, the flow trims and validates the epic and bullet inputs. `resolve_bullet`
reads the backlog file selected by the configured document roots; an unreadable backlog is treated
as having no matching entries. It compares the supplied reference, after removing one surrounding
pair of square brackets for ID lookup, against each parsed backlog bullet's ID, text, or full
bracketed text. A match returns the backlog ID and trimmed bullet text with `from_backlog: true`.
When there is no match, a single-token identifier is retained as-is; other literal text receives a
lowercase kebab-case ID truncated to 60 characters. Those fallback results retain
`from_backlog: false`. The resolver returns this `ResolvedBullet` payload, and the caller uses its
ID, source text, and provenance to construct the edit intent. It returns an
`add-story` intent containing the source id, source text, backlog provenance, parent epic, change
reason, and force flag. A blank epic or bullet fails before resolution. For a remove, it trims the
story slug, looks it up through Ostler, derives the parent epic and current status, and returns a
`remove-story` intent. An unknown or blank story fails, and started work is refused unless force is
explicit. Any action other than `add` or `remove` fails. This phase performs no graph mutation.

- code: `workflows/src/workhorse_workflows/author/story_edit/flow.py::StoryEdit.start`
- code: `workflows/src/workhorse_workflows/author/main/nodes/intake.py::adopt_backlog`
- code: `workflows/src/workhorse_workflows/author/story_edit/nodes.py::resolve_story_intent`
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::resolve_bullet`
