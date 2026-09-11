---
type: concept
slug: audit-result-field-roles
title: Audit result field roles
---
# Audit result field roles

`AuditResult` carries complementary fields rather than alternative representations of its audit
outcome. `findings` is the verdict: an empty list is a pass by construction. `status` is
agent-reported free-text status, and `notes` is an explanatory summary rather than a verdict.

The schema assigns all three fields to the same reply record, but neither its declarations nor its
class documentation establishes a preference, deprecation, or replacement relationship among
them. A reader chooses the field for the needed role and must not substitute `status` or `notes`
for `findings` when determining whether an audit passed.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditResult`
- rule: use `findings` to determine the audit verdict, `status` for agent-reported status, and `notes` for explanatory summary; none substitutes for another

## undocumented_files

`undocumented_files` is the behavior audit's parallel to `findings`: a tuple of source
file paths whose exported symbols no claim in the book cites. The field is the
authoritative coverage verdict for the source side — `coverage_complete` derives from the
same join (`Ostler.coverage`) and `findings` is empty by construction when the audit
clears — and an empty `undocumented_files` is a pass for that question by the same logic
that an empty `findings` is a pass for the audit verdict.

Like `findings`, `status`, and `notes`, `undocumented_files` is a role rather than a
redundant representation of the same outcome. It is read in the same operation that
reads `findings` and is computed in the same operation that computes `findings`, but
neither is a substitute for the other: a result with empty `findings` and a non-empty
`undocumented_files` indicates a verdict-clean audit over a book that does not yet
document some source file's behavior, which is a different defect shape than a populated
`findings` list.

The asymmetry that needs to be stated explicitly: the audit populates `undocumented_files`
from `code:` citations only (`extract_book` in `ostler/ostler/behavior.py:201`, reading
`node.meta.get("code")` at line 233 — `tests:` citations never enter `cited_paths`). The
coverage inventory's `skipped` predicate
(`workflows/src/workhorse_workflows/okf_builder/main/nodes/coverage.py::skipped`,
documented under [Source inventory filtering](source-inventory-filter.md))
removes `tests/` directories and test-suffixed / test-prefixed filenames from the unit
set before the join, so the same test file is excluded by the coverage inventory and
reported by the behavior audit when its only citation is `tests:`. The two predicates
answer different questions and the asymmetry is intentional — see
[OKF-builder audit module](okf-builder-audit-module.md) for the rationale.

- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::BehaviorAuditOutcome.undocumented_files`
