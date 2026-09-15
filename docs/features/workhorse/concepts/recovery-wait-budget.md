---
type: concept
slug: recovery-wait-budget
title: Recovery wait budget
---
# Recovery wait budget

One agent-node visit owns cumulative wait ledgers for cap waits, transient retries, reframes, and
executable-start retries. Nested helpers reserve time before sleeping, so retry layers cannot reset
the same run-level allowance by calling one another.

- code: `workhorse/workhorse/runner/waits.py::RecoveryWaitBudget` @d0c5459fe618
- code: `workhorse/workhorse/runner/waits.py::recovery_wait_scope` @d0c5459fe618
- code: `workhorse/workhorse/runner/waits.py::active_recovery_wait_budget` @d0c5459fe618
- code: `workhorse/workhorse/runner/waits.py::RecoveryWaitBudgetExceeded` @d0c5459fe618
- tests: `workhorse/tests/test_agent_recovery.py::test_retry_wait_budget_is_shared_across_output_retries`,
  `workhorse/tests/test_agent_recovery.py::test_reframe_wait_budget_is_cumulative_for_the_node`
- detail: [AgentRunner.run](run-agent.md)
- detail: [Recovery wait budget documentation](recovery-wait-budget-documentation.md)

## Fields

### limits
- type: `dict[WaitKind, float]`
- required: true
- verify: json_path(path="$.limits.cap", matches="^[0-9]+(?:\\.[0-9]+)?$")
- semantics: immutable-by-convention configured maximum seconds for `cap`, `retry`, `reframe`, and `exec-retry`
- verify: count(subject="recovery ledger category limits", equals=4)
- code: `workhorse/workhorse/runner/waits.py::RecoveryWaitBudget` @d0c5459fe618
- detail: [Recovery wait budget ledgers](recovery-wait-budget-ledgers.md)

### spent
- type: `dict[WaitKind, float]`
- default: `{}`
- verify: count(subject="fresh recovery ledger spent entries", equals=0)
- required: false
- semantics: seconds already reserved in each category
- verify: json_path(path="$.spent.retry", equals=1.0)
- code: `workhorse/workhorse/runner/waits.py::RecoveryWaitBudget` @d0c5459fe618
- detail: [Recovery wait budget ledgers](recovery-wait-budget-ledgers.md)

## Methods

### from_resilience
- sig: `RecoveryWaitBudget.from_resilience(resilience: AgentResilience) -> RecoveryWaitBudget`
- does: copies the four category limits from run resilience into the recovery ledger
- verify: count(subject="recovery ledger category limits", equals=4)
- does: starts the fresh recovery ledger with no spent reservations
- verify: count(subject="fresh recovery ledger spent entries", equals=0)
- returns: a mutable recovery ledger
- code: `workhorse/workhorse/runner/waits.py::RecoveryWaitBudget.from_resilience` @d0c5459fe618

### consume
- sig: `RecoveryWaitBudget.consume(kind: WaitKind, requested_s: float) -> None`
- does: reserves the requested non-negative finite wait when it fits the category allowance
- verify: json_path(path="$.spent.retry", equals=1.0)
- raises: `RecoveryWaitBudgetExceeded` before recording a reservation that exceeds the remaining allowance
- verify: unchanged(subject="RecoveryWaitBudget spent ledger")
- code: `workhorse/workhorse/runner/waits.py::RecoveryWaitBudget.consume` @d0c5459fe618

### recovery_wait_scope
- sig: `recovery_wait_scope(budget: RecoveryWaitBudget) -> Iterator[None]`
- does: makes one ledger visible to nested backend and process calls
- returns: restores the previous context value when the scope exits
- verify: unchanged(subject="active recovery wait context")
- code: `workhorse/workhorse/runner/waits.py::recovery_wait_scope` @d0c5459fe618

### active_recovery_wait_budget
- sig: `active_recovery_wait_budget() -> RecoveryWaitBudget | None`
- does: reads the current context-local ledger
- verify: json_path(path="$.active_is_scope_budget", equals=True)
- returns: the active ledger or `None` outside a recovery scope
- verify: json_path(path="$.outside_scope.type", equals="NoneType")
- code: `workhorse/workhorse/runner/waits.py::active_recovery_wait_budget` @d0c5459fe618

### RecoveryWaitBudgetExceeded
- sig: `RecoveryWaitBudgetExceeded(kind: WaitKind, budget_s: float, spent_s: float, requested_s: float)`
- does: identifies the category and amounts that prevented another recovery wait
- verify: json_path(path="$.error.message", matches="^(cap|retry|reframe|exec-retry) wait budget exhausted: spent [0-9.]+s of [0-9.]+s; next recovery requires [0-9.]+s$")
- returns: a `BackendInvocationError`
- verify: json_path(path="$.error.type", equals="BackendInvocationError")
- returns: a non-transient error
- verify: json_path(path="$.error.transient", equals=false)
- code: `workhorse/workhorse/runner/waits.py::RecoveryWaitBudgetExceeded` @d0c5459fe618
