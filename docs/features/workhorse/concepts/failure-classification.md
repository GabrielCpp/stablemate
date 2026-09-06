---
type: concept
slug: failure-classification
title: Agent turn failure classification
---
# Agent turn failure classification

Finished backend turns are classified once, centrally, so every CLI receives the same recovery
semantics. Scheduled caps take precedence over timeouts; context overflow takes the compaction
path; ordinary transient failures may retry; deterministic failures stop immediately.

- code: `workhorse/workhorse/runner/failure.py::classify_turn`
- code: `workhorse/workhorse/runner/failure.py::error_kind`
- code: `workhorse/workhorse/runner/failure.py::BackendInvocationError`
- code: `workhorse/workhorse/runner/failure.py::OutputParseError`
- detail: [AgentRunner.run](run-agent.md)
- detail: [AgentRunner.turn](agent-turn.md)

## Methods

### classify_turn
- sig: `classify_turn(backend_name: str, node_id: str, *, result_text: str | None, diagnostics: str, timed_out: bool, returncode: int, timeout: float, session_id: str | None = None, session_id_path: Path | None = None, rate_limited: bool = False, rate_reset_at: float | None = None) -> str`
- does: raises a cap error when a structured rate-limit signal or cap marker is present
- verify: json_path(path="$.error.message", matches="usage/spending cap reached")
- does: raises a transient timeout error when the watchdog timed out without a transient provider diagnostic
- verify: json_path(path="$.error.message", matches="Timeout waiting for result")
- does: raises an overflow error for context-window markers and records the session for compaction
- verify: json_path(path="$.error.overflow", equals=true)
- does: raises a transient or deterministic invocation error for non-zero exit according to diagnostics
- verify: json_path(path="$.error.message", matches="CLI exited with code")
- does: raises a transient error for an empty result and returns non-empty result text
- verify: json_path(path="$.error.transient", equals=true)
- raises: `BackendInvocationError` carrying `transient`, `overflow`, `timed_out`, and optional `reset_at` classification
- verify: json_path(path="$.error.type", equals="BackendInvocationError")
- returns: the original non-empty result text
- verify: json_path(path="$.result", matches=".+")
- code: `workhorse/workhorse/runner/failure.py::classify_turn`
- tests: `workhorse/tests/test_failure_handoff.py::test_classify_turn_preserves_cap_before_timeout`

### error_kind
- sig: `error_kind(exc: BaseException) -> str`
- does: maps parse, overflow, cap, timeout, transient, and fatal failures to one low-cardinality label
- verify: json_path(path="$", matches="^(parse|overflow|cap|timeout|transient|fatal)$")
- returns: one of `parse`, `overflow`, `cap`, `timeout`, `transient`, or `fatal`
- verify: json_path(path="$", matches="^(parse|overflow|cap|timeout|transient|fatal)$")
- code: `workhorse/workhorse/runner/failure.py::error_kind`

### is_transient
- sig: `is_transient(diagnostics: str) -> bool`
- does: recognizes only configured retryable diagnostic markers case-insensitively
- verify: json_path(path="$", equals=true)
- returns: whether the diagnostic is retryable
- verify: json_path(path="$", equals=false)
- code: `workhorse/workhorse/runner/failure.py::is_transient`

### is_cap
- sig: `is_cap(diagnostics: str) -> bool`
- does: recognizes scheduled usage or spending-cap markers, excluding short rate-limit markers
- verify: json_path(path="$", equals=true)
- returns: whether the diagnostic names a scheduled cap
- verify: json_path(path="$", equals=false)
- code: `workhorse/workhorse/runner/failure.py::is_cap`

### is_context_overflow
- sig: `is_context_overflow(diagnostics: str) -> bool`
- does: recognizes exhausted context-window and large-image markers
- verify: json_path(path="$", equals=true)
- returns: whether compaction is the appropriate recovery
- verify: json_path(path="$", equals=false)
- code: `workhorse/workhorse/runner/failure.py::is_context_overflow`

### is_unresumable_session
- sig: `is_unresumable_session(diagnostics: str) -> bool`
- does: recognizes a dead or unavailable session id
- verify: json_path(path="$", equals=true)
- returns: whether the caller should discard the id and retry fresh without spending reframe budget
- verify: json_path(path="$", equals=false)
- code: `workhorse/workhorse/runner/failure.py::is_unresumable_session`

### rate_limit_info
- sig: `rate_limit_info(event: dict) -> tuple[bool, float | None]`
- does: reads `rate_limit_info.status` to determine blocked status
- verify: json_path(path="$.result.blocked", equals=true)
- does: reads `rate_limit_info.resetsAt` when present
- verify: json_path(path="$.result.reset_at", equals=1780000000.0)
- returns: the blocked status
- verify: json_path(path="$.result.blocked", equals=true)
- returns: a numeric reset epoch when usable
- verify: json_path(path="$.result.reset_at", equals=1780000000.0)
- code: `workhorse/workhorse/runner/failure.py::rate_limit_info`

### record_session_map
- sig: `record_session_map(session_id_path: Path | None, node_id: str, session_id: str | None, backend: str = "") -> None`
- does: records the node-to-session mapping with visit key, timestamp, backend, and observed git head
- verify: persists(subject="the node-to-session mapping manifest row")
- does: stamps the active turn span with the session id
- verify: emitted(event="session id attribute on active agent-turn span", count=1)
- does: requests transcript capture for the recorded session
- verify: emitted(event="session transcript capture", count=1)
- returns: `None`, including when persistence or capture fails
- verify: json_path(path="$.result", equals=null)
- code: `workhorse/workhorse/runner/failure.py::record_session_map`

### BackendInvocationError
- sig: `BackendInvocationError(message: str, *, transient: bool = False, overflow: bool = False, timed_out: bool = False, reset_at: float | None = None)`
- does: carries the classification consumed by the recovery ladder
- returns: a runtime error value with the supplied flags
- code: `workhorse/workhorse/runner/failure.py::BackendInvocationError`

### OutputParseError
- sig: `OutputParseError(message: str)`
- does: identifies an agent answer that cannot satisfy the declared output contract
- verify: json_path(path="$.error.type", equals="OutputParseError")
- returns: a distinct runtime error consumed by same-session parse retry and reframing
- verify: json_path(path="$.error.kind", equals="parse")
- code: `workhorse/workhorse/runner/failure.py::OutputParseError`
