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
For an add, the flow adopts unnamed backlog bullets, trims and validates the epic and bullet inputs,
resolves the supplied id, source text, or literal against the configured backlog, and returns an
`add-story` intent containing the source id, source text, backlog provenance, parent epic, change
reason, and force flag. A blank epic or bullet fails before resolution. For a remove, it trims the
story slug, looks it up through Ostler, derives the parent epic and current status, and returns a
`remove-story` intent. An unknown or blank story fails, and started work is refused unless force is
explicit. Any action other than `add` or `remove` fails. This phase performs no graph mutation.

- code: `workflows/src/workhorse_workflows/author/story_edit/flow.py::StoryEdit.start`
- code: `workflows/src/workhorse_workflows/author/main/nodes/intake.py::adopt_backlog`
- code: `workflows/src/workhorse_workflows/author/story_edit/nodes.py::resolve_story_intent`
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::resolve_bullet`
