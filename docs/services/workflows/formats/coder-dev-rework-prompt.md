---
type: format
slug: coder-dev-rework-prompt
title: Coder dev-rework prompt
---
# Coder dev-rework prompt

- file: `workflows/src/workhorse_workflows/coder/dev/prompts/dev-rework.md`
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev._sent_back` @eb79b9ed3e8e
- detail: [coder development flow](../flows/coder-dev.md)
- detail: [coder dev-story prompt](coder-dev-story-prompt.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_finding_qa_filed_in_the_parent_run_reaches_the_dev_turn`

The dev-rework envelope is the dev turn once QA has filed a finding against the work item. It
extends the dev-story envelope and keeps its inputs, its seats, its triage and fixes, its answer
file and its result. It replaces three parts. The opening tells the owner that QA sent the story
back. The findings section says that QA saw each defect in one case, and that the fix covers
every case of the criterion it breaks. The steps start from the findings instead of the plan:
read each finding against its criterion, reopen the earlier declines and tests on the same code,
triage, fix at the cause, verify and rerun the failed QA scenarios, rewrite the walk entries the
fixes touched, review this turn's commits, and answer. The turn takes the same arguments and
returns the same `DevResult` as the dev-story envelope.
