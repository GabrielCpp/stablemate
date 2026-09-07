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
- detail: [Turn usage model](turn-usage-model.md)
- detail: [OpenTelemetry instrumentation](telemetry-instrumentation.md)

## Fields

### input_tokens
- type: `int | None`
- default: `None`
- verify: json_path(path="$.input_tokens", absent=true)
- required: false
- verify: json_path(path="$.input_tokens", absent=true)
- semantics: canonical input-token count
- verify: json_path(path="$.input_tokens", matches="^[0-9]+$")
- semantics: absent input-token reports remain unreported
- verify: json_path(path="$.input_tokens", absent=true)
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`
- detail: [turn usage measurements](turn-usage-measurements.md)

### output_tokens
- type: `int | None`
- default: `None`
- verify: json_path(path="$.output_tokens", absent=true)
- required: false
- verify: json_path(path="$.output_tokens", absent=true)
- semantics: canonical output-token count
- verify: json_path(path="$.output_tokens", equals=33)
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`
- detail: [turn usage measurements](turn-usage-measurements.md)

### cache_read_input_tokens
- type: `int | None`
- default: `None`
- verify: json_path(path="$.cache_read_input_tokens", absent=true)
- required: false
- verify: json_path(path="$.cache_read_input_tokens", absent=true)
- semantics: input tokens served from cache
- verify: json_path(path="$.cache_read_input_tokens", equals=8000)
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`
- detail: [turn usage measurements](turn-usage-measurements.md)

### cache_creation_input_tokens
- type: `int | None`
- default: `None`
- verify: json_path(path="$.cache_creation_input_tokens", absent=true)
- required: false
- verify: json_path(path="$.cache_creation_input_tokens", absent=true)
- semantics: input tokens written to cache
- verify: json_path(path="$.cache_creation_input_tokens", equals=500)
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`
- detail: [turn usage measurements](turn-usage-measurements.md)

### reasoning_output_tokens
- type: `int | None`
- default: `None`
- verify: json_path(path="$.reasoning_output_tokens", absent=true)
- required: false
- verify: json_path(path="$.reasoning_output_tokens", absent=true)
- semantics: reasoning tokens when the harness reports them
- verify: json_path(path="$.reasoning_output_tokens", equals=0)
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`
- detail: [turn usage measurements](turn-usage-measurements.md)

### total_cost_usd
- type: `float | None`
- default: `None`
- verify: json_path(path="$.total_cost_usd", absent=true)
- required: false
- verify: json_path(path="$.total_cost_usd", absent=true)
- semantics: reported monetary cost is preserved
- verify: json_path(path="$.total_cost_usd", equals=0.00089642)
- semantics: reported zero remains zero rather than becoming absent
- verify: json_path(path="$.total_cost_usd", equals=0.0)
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`
- detail: [turn usage measurements](turn-usage-measurements.md)

### duration_ms
- type: `int | None`
- default: `None`
- verify: json_path(path="$.duration_ms", absent=true)
- required: false
- verify: json_path(path="$.duration_ms", absent=true)
- semantics: latest reported duration, not a sum of per-step durations
- verify: json_path(path="$.duration_ms", equals=900)
- code: `workhorse/workhorse/runner/usage.py::TurnUsage`
- detail: [turn usage measurements](turn-usage-measurements.md)

## Methods

### normalize
- sig: `normalize(event: dict[str, Any]) -> TurnUsage`
- does: finds token-shaped data in known containers or bounded nested payloads
- verify: json_path(path="$.input_tokens", equals=6337)
- does: maps aliases and nested cache keys to canonical names
- verify: json_path(path="$.cache_read_input_tokens", equals=8000)
- does: reads reported cost without raising for unknown event shapes
- verify: json_path(path="$.total_cost_usd", equals=0.00089642)
- does: reads reported duration without raising for unknown event shapes
- verify: json_path(path="$.duration_ms", equals=4542)
- returns: a `TurnUsage` with absent measurements left as `None`
- verify: json_path(path="$.input_tokens", absent=true)
- code: `workhorse/workhorse/runner/usage.py::normalize`

### token_counts
- sig: `TurnUsage.token_counts() -> dict[str, int]`
- does: removes unreported token fields without replacing them with zero
- verify: removed(subject="unreported token fields from token_counts()")
- verify: json_path(path="$.token_counts.output_tokens", absent=true)
- returns: canonical token fields that were reported
- verify: json_path(path="$.token_counts.input_tokens", equals=12)
- code: `workhorse/workhorse/runner/usage.py::TurnUsage.token_counts`

### merge
- sig: `TurnUsage.merge(part: TurnUsage) -> TurnUsage`
- does: sums reported token quantities into the accumulated usage value
- verify: json_path(path="$.input_tokens", equals=4200)
- does: sums reported cost quantities into the accumulated usage value
- verify: json_path(path="$.total_cost_usd", equals=0.035)
- does: preserves missing values
- verify: json_path(path="$.reasoning_output_tokens", absent=true)
- does: replaces duration with the latest reported duration
- verify: json_path(path="$.duration_ms", equals=900)
- returns: a new accumulated usage value
- verify: json_path(path="$.input_tokens", equals=4200)
- code: `workhorse/workhorse/runner/usage.py::TurnUsage.merge`

### is_empty
- sig: `TurnUsage.is_empty -> bool`
- does: treats duration alone as no usage
- verify: json_path(path="$.is_empty", equals=true)
- returns: `true` when neither tokens nor cost was reported
- verify: json_path(path="$.is_empty", equals=true)
- code: `workhorse/workhorse/runner/usage.py::TurnUsage.is_empty`
