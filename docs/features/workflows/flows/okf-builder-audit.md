---
type: flow
slug: okf-builder-audit
title: OKF-builder audit workflow
---
# OKF-builder audit workflow

- start: a source scope (files, directories, service filter) and an optional turn budget
- steps:
  - [assess-audit](#assess-audit)
  - [audit-packet-review](#audit-packet-review)
- end: a behavior audit report showing assessed packets, unaudited packets (if budget exhausted), repairs discovered, and schema limitations
- verify: http_status(code=200, title="Assessment complete")
- detail: [okf-builder audit module](../concepts/okf-builder-audit-module.md)
- tests: none

## Assess audit

Rebuild the audit packet scope from current source and book, reusing only receipts bound to the current review contract.

- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::assess_audit`
- detail: [assess_audit entry points](../concepts/assess-audit-entry-points.md)

## Audit packet review

On each pass:

1. Run preparation once: read source and book, write `preparation.json` and one `packet.json`
   per selected packet under `<run_dir>/behavior-audit/<digest>/`. Gate to the operator if the
   evidence is unreadable, or finish the run once no packets remain.
2. Take the next pending packet. If it carries no candidates and no claims, record an empty
   verdict without dispatching to the reviewer
3. Otherwise, if a turn budget is set and already spent, stop the run and record the packet and
   any that follow as unaudited
4. Otherwise spend one turn: dispatch the packet, and the previous failure as feedback on a retry,
   to the reviewer agent, and persist the returned verdict, report, and review contract binding
5. If the review contract changed mid-pass, or the reviewer turn was invalid or failed, retry once
   with the failure recorded as feedback; a second failure on the same packet gates to the
   operator instead of retrying again
6. Continue to the next pass; the iteration scans receipts against the prepared packets cached
   from step 1, so the per-packet work is receipt lookup rather than source and book reads

- code: `workflows/src/workhorse_workflows/okf_builder/audit/flow.py::Audit.start`

