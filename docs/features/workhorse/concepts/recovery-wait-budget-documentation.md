---
type: concept
slug: recovery-wait-budget-documentation
title: Recovery wait budget documentation
---
# Recovery wait budget documentation

`RecoveryWaitBudget` is one mutable ledger with configured `limits` and accumulated `spent`
entries, not two alternative implementations. Its source defines both fields on the same class and
uses them together when `consume` checks and records a reservation.

Use [Recovery wait budget](recovery-wait-budget.md) to understand the ledger's visit scope,
construction, reservation operation, and exhaustion error. Use [Recovery wait budget
ledgers](recovery-wait-budget-ledgers.md) when selecting the field needed for a particular
calculation: `limits` supplies the configured allowance and `spent` supplies already-reserved
seconds. Neither document supersedes the other, and the source records no ranking between them.

- rule: use the recovery wait budget concept for the ledger lifecycle and API; use the ledgers concept to distinguish configured allowances from consumed reservations; neither is a replacement for the other
