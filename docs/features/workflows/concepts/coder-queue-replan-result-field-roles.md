---
type: concept
slug: coder-queue-replan-result-field-roles
title: Coder queue replan result field roles
---
# Coder queue replan result field roles

`ReplanResult` records one operator-directed epic rewrite. Its `status` is the outcome the
workflow uses to distinguish a re-grounded epic from one that must remain blocked; `notes` is the
one-line account of what was re-grounded or what the answer left undecided. The fields are
complementary parts of one reply, not competing interfaces, and the source declares no ranking
between them.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::ReplanResult`
- rule: read `status` to determine the replan outcome and `notes` to read its context; no field is preferred or deprecated because both describe the same replan reply
