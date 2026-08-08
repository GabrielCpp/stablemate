---
type: flow
slug: author-story-edit
title: Author story edit
---
# Author story edit

- start: An operator requests one story addition or removal through `workhorse-author run
  story-edit`. Add names an existing epic and a backlog id or literal request; remove names an
  existing story and requires `force: true` when work has advanced beyond Not started. Any additional
  story or unrelated seed removal also requires force; frozen scope must be unfrozen first.
- steps:
  1. Author resolves configured paths and adopts unnamed backlog bullets before resolving an add.
  2. A deterministic preflight resolves the source item or the removed story's parent epic, status,
      covered seeds, configured epic root, and binding outcome. It refuses unknown entities and
      unauthorized removal before invoking a model.
  3. Story edit checkpoints that result as a typed add-story or remove-story intent and hands it to
     the author epic-edit flow. It performs no direct story mutation.
  4. Epic edit must update the parent epic's scope and user journeys, reconcile seeds, coverage and
     dependencies, and write every affected story. The requested add must finish covered; the
     requested removal must finish absent.
  5. Removing the final story also removes its explicitly dropped seeds. When no seeds and stories
     remain, graph-safe deletion removes the epic and its milestone and legacy queue references.
- end: The story operation, parent epic narrative, resulting story graph, backlog, and milestone
  ownership agree, and the whole documentation graph passes integrity before the edit is committed.
- verify: workflows/tests/author/test_workflow.py::test_story_edit_add_authors_one_story_and_commits
- verify: workflows/tests/author/test_workflow.py::test_story_edit_remove_reconciles_remaining_epic_scope_and_journey
- verify: workflows/tests/author/test_workflow.py::test_story_edit_remove_deletes_an_unstarted_story_and_commits
- verify: workflows/tests/author/test_workflow.py::test_story_edit_mutates_the_overridden_epics_root
- code: workflows/src/workhorse_workflows/author/story_edit/flow.py::StoryEdit
- code: workflows/src/workhorse_workflows/author/story_edit/nodes.py::resolve_story_intent
