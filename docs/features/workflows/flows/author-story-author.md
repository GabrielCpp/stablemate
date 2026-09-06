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

- start: an operator supplies an existing epic and a non-empty story slug
- start: the selected story is resolvable under that epic in the configured Ostler graph
- start: the repository root can be resolved from the optional `repo_dir`
- steps:
  - [prepare-story](#prepare-story)
  - [design-mockup](#design-mockup)
  - [write-story](#write-story)
  - [check-story](#check-story)
  - [audit-story](#audit-story)
  - [story-feedback](#story-feedback)
- end: the selected story has passed structural, grounding, and independent audit checks
- end: a passing audit receipt records the SHA-256 digest of the exact story bytes
- end: blocked or exhausted work is parked in an operator-awaiting context or returns a blocked result
- verify: count(subject="prepared story-author targets", equals=1)
- verify: created(subject="audit-receipt.json")
- verify: json_path(path="$.status", equals="authored")
- detail: [author story-author subflow](../concepts/author-story-author-subflow.md)
- tests: `workflows/tests/author/story_author/test_flow.py::test_flow_prepares_explicit_story_before_authoring_without_git_side_effects`

## Steps

### prepare-story
- kind: prepare
- run: resolve the explicit `epic` and `story` parameters and scaffold missing story sections
- verify: [prepare_story](../concepts/author-story-author-subflow.md#prepare_story)

### design-mockup
- kind: run
- run: invoke the story-local design prompt when `check_mockup_needed` reports `required`
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

### audit-story
- kind: verify
- run: invoke the independent story audit and route findings to bounded rework
- verify: [audit_story](../concepts/author-story-author-subflow.md#audit_story)

### story-feedback
- kind: verify
- run: poll feedback, rework when feedback exists, or record the passing audit receipt
- verify: [story_feedback](../concepts/author-story-author-subflow.md#story_feedback)
