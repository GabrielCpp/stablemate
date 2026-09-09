---
type: format
slug: prices-config
title: Prices configuration file
---
# Prices configuration file

Override or extend the built-in [pricing module](concepts/groom-prices-module.md) rate table by adding vendor rate cards as TOML. The file is read once per process and cached, so a rate card change requires a new `groom` invocation. A malformed file is logged and ignored rather than failing startup, so pricing becomes unavailable rather than blocking the dashboard.

- file: `~/.config/stablemate/prices.toml` (or `$GROOM_PRICES` if set)
- config: per-operator, per-vendor, keyed by model id
- code: groom/groom/prices.py::_overrides
- detail: [Price dataclass](concepts/groom-prices-module.md#price)
- tests: groom/tests/test_prices.py

## Format

A top-level `[models]` table, with one subtable per model id:

```toml
[models."gpt-5.6-luna"]
input = 0.20          # required: $ per million input tokens
output = 1.20         # required: $ per million output tokens
cache_read = 0.02     # optional; defaults to input * 0.1
cache_write = 0.25    # optional; defaults to input * 2.0
```

The entry schema:

- `models` — required top-level table holding all model overrides
  - `"<model-id>"` — a model name, case-insensitive, date-suffix stripped on lookup (e.g. `"claude-opus-5-20250909"` is normalized to `"claude-opus-5"`)
    - `input` — required field, float ≥ 0; dollars per million input tokens
    - `output` — required field, float ≥ 0; dollars per million output tokens
    - `cache_read` — optional field, float ≥ 0; defaults to `input * 0.1`; dollars per million cache-hit tokens
    - `cache_write` — optional field, float ≥ 0; defaults to `input * 2.0`; dollars per million cache-creation tokens

Entries without `input` or `output` are logged and skipped. Non-numeric rates are treated as malformed and skipped. Duplicate model names use the last occurrence. Models in this file override the built-in table entirely.

## Fields

### field: input

Dollars per million input tokens at this vendor's rates.

- type: `float`
- required: true
- semantics: input token cost in USD
- semantics: must be non-negative
- semantics: replaces the built-in rate for this model
- code: groom/groom/prices.py::_overrides
- detail: [Price.input](concepts/groom-prices-module.md#field-input)
- detail: [Prices override entry fields](concepts/prices-override-entry-fields.md)

### field: output

Dollars per million output tokens at this vendor's rates.

- type: `float`
- required: true
- semantics: output token cost in USD
- semantics: must be non-negative
- semantics: replaces the built-in rate for this model
- code: groom/groom/prices.py::_overrides
- detail: [Price.output](concepts/groom-prices-module.md#field-output)
- detail: [Prices override entry fields](concepts/prices-override-entry-fields.md)

### field: cache_read

Dollars per million cache-hit tokens at this vendor's rates.

- type: `float`
- default: `input * 0.1`
- required: false
- semantics: cache-read cost in USD
- semantics: when omitted, derived from input rate at Anthropic's 0.1x multiplier
- code: groom/groom/prices.py::_overrides
- detail: [Price.cache_read](concepts/groom-prices-module.md#field-cache_read)
- detail: [Prices override entry fields](concepts/prices-override-entry-fields.md)

### field: cache_write

Dollars per million cache-creation tokens at this vendor's rates.

- type: `float`
- default: `input * 2.0`
- required: false
- semantics: cache-write cost for hour-TTL contexts in USD
- semantics: when omitted, derived from input rate at Anthropic's 2.0x multiplier
- code: groom/groom/prices.py::_overrides
- detail: [Price.cache_write](concepts/groom-prices-module.md#field-cache_write)
- detail: [Prices override entry fields](concepts/prices-override-entry-fields.md)

