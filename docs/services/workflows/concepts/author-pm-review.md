---
type: concept
slug: author-pm-review
title: Author PM review
---
# Author PM review

The `PMReview` flow is the one reviewer every Author stage uses. A stage hands it the output to judge, and it returns whether every angle of that stage passed, the findings when one did not, and the path of the [PM receipt](../formats/pm-receipt.md) when all did. It replaces the per-stage reviewers, auditors and coverage judges.

Each review runs in a fresh agent session that no earlier turn touched. The reviewer reads the milestone, its [ledger](../formats/pm-ledger.md) and the stage's output, and it never edits a file. The reply holds one verdict for every [angle](author-pm-angles.md) of the stage. A reply that skips an angle, repeats one or names one the stage does not have is refused and asked again.

When the agent CLI can spawn subagents, the review runs from the delegated prompt: the parent spawns one subagent per angle and merges their verdicts. Otherwise it runs from the inline prompt, which asks one session to judge each angle in turn. Both prompts share the same inputs, rules and angle files.

- code: `workflows/src/workhorse_workflows/author/pm/flow.py::PMReview` @71c759122da8
- code: `workflows/src/workhorse_workflows/author/pm/flow.py::PMReview.start` @71c759122da8
- code: `workflows/src/workhorse_workflows/author/pm/flow.py::PMReview.review` @71c759122da8
- code: `workflows/src/workhorse_workflows/author/pm/flow.py::complete` @71c759122da8
- code: `workflows/src/workhorse_workflows/author/pm/flow.py::format_findings` @71c759122da8
- code: `workflows/src/workhorse_workflows/author/pm/nodes/receipt.py::record_pm_receipt` @5c73dfc30d46
- tests: `workflows/tests/author/pm/test_pm.py::test_a_passing_review_writes_a_receipt_and_a_failing_one_does_not`
- tests: `workflows/tests/author/pm/test_pm.py::test_the_review_variant_follows_the_backend`
- tests: `workflows/tests/author/pm/test_pm.py::test_a_review_must_judge_every_angle_exactly_once`
- detail: [PM review angles](author-pm-angles.md)
- detail: [PM gap answer](author-pm-gap-answer.md)
- detail: [PM receipt](../formats/pm-receipt.md)

## Fields

### stage
- type: one of `epic-split`, `story-split`, `story`, `epic-edit-plan`
- default: empty
- required: true
- semantics: names the angle set and the stage brief the review uses
- verify: json_path(path="$.stage", equals="story")
- code: `workflows/src/workhorse_workflows/author/pm/flow.py::PMReview` @71c759122da8

### subject
- type: string
- default: empty
- required: false
- semantics: the repository path of the output under review: the milestone for `epic-split`, the epic directory for `story-split`, the `story.md` for `story`, the epic directory for `epic-edit-plan`
- verify: json_path(path="$.subject", equals="docs/milestones/m1/epics/0001-accounts/stories/0001-sign-in/story.md")
- code: `workflows/src/workhorse_workflows/author/pm/flow.py::PMReview` @71c759122da8

### prior
- type: string
- default: empty
- required: false
- semantics: the findings of the previous review of the same subject, so the reviewer checks that each was repaired
- verify: json_path(path="$.prior", equals="")
- code: `workflows/src/workhorse_workflows/author/pm/flow.py::PMReview` @71c759122da8

## Methods

### start
- sig: `start() -> Continue`
- does: refuses a stage that has no angles before any agent turn runs
- verify: json_path(path="$.failure_class", equals="pm-review-unknown-stage")
- returns: returns a continuation targeting `review`
- code: `workflows/src/workhorse_workflows/author/pm/flow.py::PMReview.start` @71c759122da8

### review
- sig: `review() -> Done`
- does: asks a high-power agent in a fresh session for one verdict per angle of the stage
- verify: count(subject="PM review turns", equals=1)
- does: runs the delegated prompt when the backend supports subagents and the inline prompt when it does not
- verify: count(subject="PM review prompt variants", equals=1)
- does: writes the receipt only when every angle passed
- verify: created(subject="pm-receipt.json")
- returns: returns whether the review passed, its findings and the receipt path
- verify: json_path(path="$.passed", equals=True)
- code: `workflows/src/workhorse_workflows/author/pm/flow.py::PMReview.review` @71c759122da8

### complete
- sig: `complete(angles: Sequence[Angle]) -> Callable[[Verdict], None]`
- does: builds the check that refuses a reply with a missing, repeated or foreign angle
- verify: json_path(path="$.error", matches="no verdict for the angles")
- code: `workflows/src/workhorse_workflows/author/pm/flow.py::complete` @71c759122da8

### format_findings
- sig: `format_findings(findings: Sequence[PMFinding]) -> str`
- does: renders each finding as `[angle] target: issue. Repair: repair`, one per line
- verify: json_path(path="$.notes", matches="^\\[[a-z-]+\\] ")
- code: `workflows/src/workhorse_workflows/author/pm/flow.py::format_findings` @71c759122da8

## Nodes

### record_pm_receipt
- sig: `record_pm_receipt(logger: logging.Logger, stage: str, subject: str, repo_dir: str = "") -> PMReceipt`
- does: binds a passing review to the exact bytes it judged and writes `pm-receipt.json`
- verify: created(subject="pm-receipt.json")
- does: writes nothing for a stage whose output is not a durable file
- verify: absent(subject="pm-receipt.json for the epic-edit-plan stage")
- code: `workflows/src/workhorse_workflows/author/pm/nodes/receipt.py::record_pm_receipt` @5c73dfc30d46
