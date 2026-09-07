---
type: concept
slug: verify-report-field-roles
title: Verify report field roles
---
# Verify report field roles

`VerifyReport` represents the result of either tri-state verifier with complementary fields rather
than alternative representations of one result. `holds` records the gate decision; `skipped`
distinguishes an unavailable prerequisite from a failed condition; `errors` carries findings for the
author flow; and `report` is the multi-line preamble read by the resolver prompt.

The schema assigns all four fields to the same result and establishes no preference, deprecation,
or replacement relationship among them. Choose the field for the required role: a skipped verifier
proceeds fail-open, while an executed verifier's decision is in `holds`; neither text field
substitutes for that decision.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::VerifyReport`
- rule: use `holds` for the gate decision, `skipped` for an unavailable prerequisite, `errors` for author-flow findings, and `report` for the resolver prompt preamble; none substitutes for another
