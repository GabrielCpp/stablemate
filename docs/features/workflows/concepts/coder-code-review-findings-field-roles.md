---
type: concept
slug: coder-code-review-findings-field-roles
title: Coder code review findings field roles
---
# Coder code review findings field roles

`CodeReviewResult.findings` has two current documentation contexts. The result-format field is
the reference for the typed value the flow retains: it is a list of `ReviewFinding` values and is
empty for every status except `findings`. The code-review-prompt field is the reference for what
the feeder reviewer must put in that same value: every reported issue carries an actionable
target, issue, repair, category, and score.

Neither field replaces the other. Use the result-format field when reading or producing the
model contract; use the prompt field when instructing or assessing the reviewer response that
must satisfy that contract. The schema declares the typed list and the prompt's response is the
producer of its entries, so no source-backed ranking or deprecation exists between them.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::CodeReviewResult.findings`
- rule: use the result-format field for the retained model contract and the prompt field for the feeder reviewer response contract; neither is a replacement for the other
