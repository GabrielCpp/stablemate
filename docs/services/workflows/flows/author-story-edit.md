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
  and its `author-story-edit` deterministic-node blueprint; the [edit intent](../formats/edit-intent.md)
  is the handoff format. Its entry points are `StoryEdit.setup`, `StoryEdit.start`, and
  `resolve_story_intent` in `workflows/src/workhorse_workflows/author/story_edit/flow.py` and
  `workflows/src/workhorse_workflows/author/story_edit/nodes.py`.

- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- steps:
  - [run](../workhorse-author.md#run)
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-author.dot")
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_add_authors_one_story_and_promotes_its_record`
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_remove_reconciles_remaining_epic_scope_and_journey`
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_remove_deletes_an_unstarted_story_and_commits`
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_follows_the_configured_epics_root`
- detail: [workhorse-author run command](../workhorse-author.md#run)

The stages, in order: [setup](#setup), [resolve the story intent](#resolve-the-story-intent), [reconcile the parent epic](author-epic-edit.md), [validate and commit](author-epic-edit.md#validate-coverage-and-commit).

The flow starts when an operator invokes `workhorse-author run story-edit` with an `action` of `add` or `remove`; or when an add request supplies an existing epic and the id or short handle of an open register record; or when a remove request supplies a non-empty existing story slug; or when a remove request for work whose status is not `Not started` supplies `force: true`; or when a plan that removes a story other than the requested story supplies `force: true`; or when a plan that removes a seed not covered by the requested story supplies `force: true`; or when a plan that removes frozen scope has been unfrozen before execution.
It ends in one of these ways: an add operation leaves the requested story covering its resolved source item; a remove operation leaves the requested story absent; the parent epic narrative and resulting story graph agree; milestone source items and references agree with the resulting graph; the record behind an added story is closed as promoted; the whole documentation graph passes integrity before the edit is committed.

## Phase Details

### Setup
`StoryEdit.setup` resolves the repository root, epics root, and feature-book path through the
configured document roots. This setup delegates to `load_config` in
`workflows/src/workhorse_workflows/author/shared/nodes/config.py`. It reads no backlog file,
because the work items live on the [debt register](../../ostler/concepts/the-debt-register.md).

### Resolve the story intent
For an add, the flow trims and validates the epic and record inputs. A blank epic or record fails
before resolution. `resolve_record` resolves the record input, a full id or a short handle, against
the register. A token that names no record fails the run, and so does a record that is not `open`.
Literal text is not a record and fails the same way. The resolver returns the record, and the caller
uses its id, summary and body to construct the edit intent. It returns an `add-story` intent
containing the record id, its summary and body, the parent epic, the change reason, and the force
flag. The change reason defaults to `Add a story for <summary>`. The epic-edit pass later closes the
record as promoted, as [promoting a record](../concepts/promote-a-record.md) describes.
For a remove, it trims the story slug, looks it up through Ostler, derives the parent epic and
current status, and returns a `remove-story` intent. An unknown or blank story fails, and started
work is refused unless force is explicit. Any action other than `add` or `remove` fails. This phase
performs no graph mutation.
The entry point is `StoryEdit.start` in
`workflows/src/workhorse_workflows/author/story_edit/flow.py`; it calls `resolve_story_intent`,
which in turn calls `resolve_record`.
