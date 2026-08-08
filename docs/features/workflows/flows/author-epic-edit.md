---
type: flow
slug: author-epic-edit
title: Author epic edit
---
# Author epic edit

- start: An operator invokes `workhorse-author run epic-edit` with an existing epic and a concrete
  product-scope change, optionally setting `force: true` for destructive reconciliation, or
  story-edit hands over a validated binding story intent.
- steps:
   1. A deterministic snapshot records current seeds, stories, statuses, covers, dependencies,
      frozen state, milestone ownership, the resolved epic root, and hashes of story bodies outside
      the requested edit.
  2. A planning-only model returns a typed complete replacement plan. The turn is forbidden from
     editing files; its plan declares journey, seed and story changes and the affected worklist.
  3. Static projected-graph validation rejects duplicate operations, missing covers or dependencies,
      cycles, orphaned active seeds, unauthorized collateral removal, frozen-scope removal,
      unsatisfied story intent, omitted affected stories, and an inconsistent empty-epic decision.
  4. Every coded finding and the rejected plan are passed to `refine-epic-edit-plan`; the model must
     return a complete replacement plan. The same static validator reruns, with three bounded passes
     before an operator gate.
  5. An independent semantic reviewer checks actor journeys, story-sized deliverables and dependency
     order only after static validation passes. Review notes use the same plan-refinement loop.
   6. Deterministic Ostler calls apply the approved seed and story graph through the snapshotted epic
      root. A delta check proves no unaffected story body changed. Existing story ids, bodies and
      statuses survive metadata updates, and empty-epic deletion can safely resume after interruption.
  7. A model rewrites only human-owned epic prose. A parsed Markdown validator requires every epic
     section and at least one journey while Ostler-owned Seeds and Stories remain structural data.
   8. Newly added and explicitly affected stories run through mockup, authoring, static validation,
      grounding and independent audit loops. A new visual reference is written only as the story's
      `mockup.html`; the OKF feature book stays read-only and no inventory is created. Unaffected
      stories are not rewritten.
  9. Per-epic coverage, semantic coverage review and whole-graph integrity pass before a backlog item
     is pruned and the edit is committed. An empty approved epic skips prose/story work and is deleted.
- end: The operator's intent is reflected consistently in epic journeys, seeds, story contracts,
  dependencies, backlog ownership and milestones, with static findings driving model correction.
- verify: workflows/tests/author/test_workflow.py::test_epic_edit_static_findings_drive_a_replacement_plan
- verify: ostler/tests/test_crud.py::test_update_story_changes_edges_without_touching_story_body
- verify: ostler/tests/test_crud.py::test_delete_epic_removes_its_milestone_reference
- verify: workflows/tests/author/epic_edit/test_edit.py::test_plan_requires_force_for_removals_beyond_requested_story
- verify: workflows/tests/author/test_workflow.py::test_story_edit_mutates_the_overridden_epics_root
- verify: ostler/tests/test_crud.py::test_delete_epic_finishes_cleanup_after_interruption
- code: workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit
- code: workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::validate_edit_plan
- code: workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::apply_edit_plan
