---
type: concept
slug: assess-audit-entry-points
title: assess_audit entry points
---
# assess_audit entry points

`assess_audit` has two current call sites, and neither supersedes the other — this is a
competition the source does not settle, recorded as one rather than resolved by invention.

- `main/flow.py::OkfBuilder.commit` calls it as the commit gate for the whole-book builder flow:
  before `commit_book` runs, the current source and book must clear a fresh audit receipt, or
  the flow loops back into `semantic_audit` instead of publishing.
- `audit/flow.py::Audit.start` calls it as the entry step of the standalone `Audit` workflow,
  whose whole job is running this same assessment on its own turn budget, independent of any
  builder run.

[okf-builder-audit-module.md](okf-builder-audit-module.md) documents `assess_audit` itself — its
signature, return shape, and behaviour — and is the node either call site should read to
understand what the call does. [okf-builder-audit.md](../flows/okf-builder-audit.md) documents
the standalone `Audit` workflow that exists to drive it. A reader who wants "what does
`assess_audit` do" wants the first; a reader who wants "how do I run an audit pass on demand"
wants the second. Neither is a stand-in for the other, and no rule chooses between them.

- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::assess_audit`
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.commit`
- rule: choose `Audit.start` to run a turn-budgeted standalone audit pass, and `OkfBuilder.commit` to gate the whole-book builder flow on a fresh audit receipt — neither is preferred or deprecated; the choice is by context, not by rank
- detail: [OKF-builder audit module](okf-builder-audit-module.md)

