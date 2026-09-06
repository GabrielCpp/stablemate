---
type: concept
slug: usage-normalization
title: Agent usage normalization
---
# Agent usage normalization

Different CLIs report tokens, cache counts, cost, and duration under incompatible names. This
module maps recognized fields to one canonical `TurnUsage` value, preserving `None` for data a
harness did not report and summing step-level reports without confusing price tables for counts.

- code: `workhorse/workhorse/runner/usage.py::TurnUsage`
- code: `workhorse/workhorse/runner/usage.py::normalize`
- tests: `workhorse/tests/test_usage.py::test_cline_reports_tokens_cost_and_duration`, `workhorse/tests/test_usage.py::test_copilot_reports_no_tokens_and_no_money`, `workhorse/tests/test_usage.py::test_opencode_steps_sum_into_one_turn`, `workhorse/tests/test_usage.py::test_a_price_table_is_not_a_token_count`
- detail: [OpenTelemetry instrumentation](telemetry-instrumentation.md)

## Fields

### input_tokens
- type: `int | None`
- default: `None`
- required: false
- semantics: canonical input-token count
- verify: json_path(path="$.input_tokens", matches="^[0-9]+$")
- semantics: absent input-token reports remain unreported
- verify: json_path(path="$.input_tokens", absent=true)
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`

### output_tokens
- type: `int | None`
- default: `None`
- required: false
- semantics: canonical output-token count
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`

### cache_read_input_tokens
- type: `int | None`
- default: `None`
- required: false
- semantics: input tokens served from cache
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`

### cache_creation_input_tokens
- type: `int | None`
- default: `None`
- required: false
- semantics: input tokens written to cache
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`

### reasoning_output_tokens
- type: `int | None`
- default: `None`
- required: false
- semantics: reasoning tokens when the harness reports them
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`

### total_cost_usd
- type: `float | None`
- default: `None`
- required: false
- semantics: reported monetary cost is preserved
- verify: json_path(path="$.total_cost_usd", equals=0.00089642)
- semantics: reported zero remains zero rather than becoming absent
- verify: json_path(path="$.total_cost_usd", equals=0.0)
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`

### duration_ms
- type: `int | None`
- default: `None`
- required: false
- semantics: latest reported duration, not a sum of per-step durations
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`

## Methods

### normalize
- sig: `normalize(event: dict[str, Any]) -> TurnUsage`
- does: finds token-shaped data in known containers or bounded nested payloads
- does: maps aliases and nested cache keys to canonical names
- does: reads cost and duration without raising for unknown event shapes
- returns: a `TurnUsage` with absent measurements left as `None`
- code: `workhorse/workhorse/runner/usage.py::normalize`

### token_counts
- sig: `TurnUsage.token_counts() -> dict[str, int]`
- does: removes unreported token fields without replacing them with zero
- returns: canonical token fields that were reported
- code: `workhorse/workhorse/runner/usage.py::TurnUsage.token_counts`

### merge
- sig: `TurnUsage.merge(part: TurnUsage) -> TurnUsage`
- does: adds reported token and cost quantities while preserving missing values
- does: replaces duration with the latest reported duration
- returns: a new accumulated usage value
- code: `workhorse/workhorse/runner/usage.py::TurnUsage.merge`

### is_empty
- sig: `TurnUsage.is_empty -> bool`
- does: treats duration alone as no usage
- returns: `true` when neither tokens nor cost was reported
- code: `workhorse/workhorse/runner/usage.py::TurnUsage.is_empty`
