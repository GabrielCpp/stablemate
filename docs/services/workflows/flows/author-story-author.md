---
type: flow
slug: author-story-author
title: Author story author
---
# Author story author

- The [author story-author subflow](../concepts/author-story-author-subflow.md) owns this directly
  runnable machine and its package-local deterministic-node blueprint. The [author workflow
  composition root](../concepts/author-workflow-composition-root.md) registers it as
  `workhorse-author run story-author`.

- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- steps:
  - [run](../workhorse-author.md#run)
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-author.dot")
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [author story-author subflow](../concepts/author-story-author-subflow.md)
- detail: [author story-author prompt contracts](../concepts/author-story-author-prompt-contracts.md)
- detail: [author PM review](../concepts/author-pm-review.md)
- tests: `workflows/tests/author/story_author/test_flow.py::test_flow_prepares_explicit_story_before_authoring_without_git_side_effects`

The stages, in order: [prepare-story](#prepare-story), [design-mockup](#design-mockup), [write-story](#write-story), [check-story](#check-story), [review](#review), [rework-story](#rework-story), [ask-pm](#ask-pm), [story-feedback](#story-feedback), [apply-feedback](#apply-feedback).

The flow starts when an operator supplies an existing epic and a non-empty story slug; or when the selected story is resolvable under that epic in the configured Ostler graph; or when the repository root can be resolved from the optional `repo_dir`.
It ends in one of these ways: the selected story has passed structural, grounding, and PM review checks; a PM receipt records the SHA-256 digest of the exact story bytes; blocked or exhausted work returns a blocked result that the Author flow keeps on the work list.

## Steps

### prepare-story
- kind: prepare
- run: resolve the explicit `epic` and `story` parameters and scaffold missing story sections
- verify: [prepare_story](../concepts/author-story-author-subflow.md#prepare_story)

### design-mockup
- kind: run
- run: invoke the story-local design prompt when `check_mockup_needed` reports `required`; a failed or missing mockup ends the run as `blocked` before `write-story`
- verify: [design_mockup](../concepts/author-story-author-subflow.md#design_mockup)
- optional: true

### write-story
- kind: run
- run: invoke the story writing prompt with the target paths and optional mockup
- verify: [write_story](../concepts/author-story-author-subflow.md#write_story)

### check-story
- kind: verify
- run: validate story structure and feature-book grounding
- verify: [check_story](../concepts/author-story-author-subflow.md#check_story)
- code: `workflows/src/workhorse_workflows/author/shared/nodes/stories.py::validate_story` @61ad4510b612
- code: `workflows/src/workhorse_workflows/author/shared/nodes/stories.py::check_story_grounding` @61ad4510b612
- code: `workflows/src/workhorse_workflows/author/shared/nodes/services.py::service_errors` @a4aea1835f7b
- code: `workflows/src/workhorse_workflows/author/shared/nodes/services.py::ui_service_names` @a4aea1835f7b

### review
- kind: verify
- run: hand the story to the PM review and route findings to bounded rework
- verify: [review](../concepts/author-story-author-subflow.md#review)
- code: `workflows/src/workhorse_workflows/author/pm/nodes/_blueprint.py::blueprint` @6147fef19ca9

### rework-story
- kind: run
- run: record the failed attempt and ask the rework prompt to revise the story
- verify: [rework_story](../concepts/author-story-author-subflow.md#rework_story)
- optional: true

### ask-pm
- kind: run
- run: hand a blocked writer's question to the PM gap answer, then resume with the answer as a note
- verify: [ask_pm](../concepts/author-story-author-subflow.md#ask_pm)
- optional: true

### story-feedback
- kind: verify
- run: poll feedback, then rework when feedback exists or finish
- verify: [story_feedback](../concepts/author-story-author-subflow.md#story_feedback)

### apply-feedback
- kind: run
- run: send operator feedback through the rework prompt and return to story checks
- verify: [apply_feedback](../concepts/author-story-author-subflow.md#apply_feedback)
- optional: true
