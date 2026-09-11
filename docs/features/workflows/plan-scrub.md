---
type: format
slug: plan-scrub
title: Plan scrub result
---
# Plan scrub result

The plan scrub result reports code-repository changes removed after a planning turn. Only paths
that became dirty after the pre-plan snapshot are charged: tracked paths are restored from `HEAD`,
new untracked files and directories are deleted, and pre-existing dirt is preserved. The docs root
is exempt because plan artifacts are expected there. Empty output means no new code-repository
mutation was found.

- file: none — in-memory workflow result
- config: pre-plan status and the resolved code repositories
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::PlanScrub`
- detail: [Coder story pipeline](concepts/story-pipeline.md)
- tests: `workflows/tests/coder/shared/test_clean_tree.py::test_the_scrub_reverts_what_the_turn_wrote_and_only_that`
- tests: `workflows/tests/coder/shared/test_clean_tree.py::test_a_turn_that_kept_to_reading_scrubs_nothing`

## Fields

### reverted
- type: `dict[str, str]`
- default: empty mapping
- required: false
- semantics: affected absolute repository paths mapped to new porcelain entries and, for tracked paths, up to 4000 characters of discarded `HEAD` diff
- verify: json_path(path="$.reverted", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::PlanScrub.reverted`
