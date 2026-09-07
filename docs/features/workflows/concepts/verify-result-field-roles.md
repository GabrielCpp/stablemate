---
type: concept
slug: verify-result-field-roles
title: Verify result field roles
---
# Verify result field roles

`VerifyResult` expresses one coverage-gate outcome through complementary fields, not
alternative implementations or aliases. Read `holds` to make the gate decision.
When it holds because no inventory exists, `nothing_surveyed` distinguishes that case
from completed coverage. When it does not hold, `verify_errors` carries the defects
that prevented coverage, while `verify_report` supplies the human-readable counts and
outcome.

No field ranks above or replaces another. Callers use the fields required for their
part of the result instead of choosing a preferred field.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::VerifyResult`
- rule: use each field for its named coverage-result aspect; no field replaces another
