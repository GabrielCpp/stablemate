---
type: concept
slug: recovery-wait-budget-ledgers
title: Recovery wait budget ledgers
---
# Recovery wait budget ledgers

`RecoveryWaitBudget` keeps two complementary ledgers for every wait category. `limits` is the
configured ceiling copied from run resilience, while `spent` records reservations made during the
current agent-node visit. They are not alternative implementations and neither replaces the other:
use `limits` to determine the allowance and `spent` to determine how much of that allowance is
already consumed before making the next reservation.

- code: `workhorse/workhorse/runner/waits.py::RecoveryWaitBudget`
- rule: use `limits` for configured category ceilings and `spent` for reservations consumed during the current agent-node visit; neither field supersedes the other
- detail: [Recovery wait budget documentation](recovery-wait-budget-documentation.md)
