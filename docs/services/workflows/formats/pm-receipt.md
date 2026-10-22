---
type: format
slug: pm-receipt
title: PM receipt
---
# PM receipt

A PM receipt is the durable proof that the product manager passed the exact bytes a stage produced. Finalize and the Author fill step accept a stage's output only when its receipt is current: it names the stage and carries the digest of what is on disk now. Any edit after the pass voids the receipt.

The receipt lives beside the output it judged: next to `story.md` for a story, in the epic directory for a story split, and in the milestone's `artifacts/` folder for the epic split.

- file: `<output directory>/pm-receipt.json`
- code: `workflows/src/workhorse_workflows/author/pm/receipt.py::write_pm_receipt` @e2e7f255aa72
- code: `workflows/src/workhorse_workflows/author/pm/receipt.py::pm_receipt_current` @e2e7f255aa72
- code: `workflows/src/workhorse_workflows/author/pm/receipt.py::receipt_target` @e2e7f255aa72
- code: `workflows/src/workhorse_workflows/author/pm/receipt.py::story_digest` @e2e7f255aa72
- code: `workflows/src/workhorse_workflows/author/pm/receipt.py::story_split_digest` @e2e7f255aa72
- code: `workflows/src/workhorse_workflows/author/pm/receipt.py::epic_split_digest` @e2e7f255aa72
- tests: `workflows/tests/author/pm/test_pm.py::test_a_receipt_is_current_only_for_its_stage_and_digest`
- detail: [Author PM review](../concepts/author-pm-review.md)

## Fields

### stage
- type: string
- required: true
- semantics: the stage whose pass this records
- verify: json_path(path="$.stage", equals="story")
- code: `workflows/src/workhorse_workflows/author/pm/receipt.py::write_pm_receipt` @e2e7f255aa72

### status
- type: literal `passed`
- required: true
- semantics: a receipt exists only for a pass
- verify: json_path(path="$.status", equals="passed")
- code: `workflows/src/workhorse_workflows/author/pm/receipt.py::write_pm_receipt` @e2e7f255aa72

### digest
- type: string
- required: true
- semantics: the sha256 the stage's output had when it passed. A story binds its bytes. A story split binds the active seed ids and each story's slug, title, covers and dependencies, so later prose edits keep the pass. An epic split binds the ordered epic list and the milestone body.
- verify: json_path(path="$.digest", matches="^[0-9a-f]{64}$")
- code: `workflows/src/workhorse_workflows/author/pm/receipt.py::write_pm_receipt` @e2e7f255aa72
