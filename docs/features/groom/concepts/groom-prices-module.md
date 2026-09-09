---
type: concept
slug: groom-prices-module
title: Groom pricing module
---
# Groom pricing module

Estimate token costs for runs using published vendor rate cards when billing data is unavailable. The module reads a built-in table of per-million rates for the models this repository uses, extended and corrected by an operator's override file. A model absent from the table is left unpriced; no averaging or guessing happens, so unpriceable turns remain visible in reports.

Each token class (input, output, cache reads, cache writes) carries its own rate, and cache defaults follow Anthropic's published multipliers (reads at 0.1x input, writes at 2.0x input for hour-TTL contexts). An estimate is kept in a separate column from actual billing data — they are different claims — and never summed together.

- code: groom/groom/prices.py
- tests: groom/tests/test_prices.py
- detail: [prices configuration file](../prices-config.md)

## Public members

### Price

Dollars per million tokens, one rate per token class. Cached reads bill at a fraction of the input rate; cached writes bill at a multiple.

- sig: `@dataclass(frozen=True) Price`
- code: groom/groom/prices.py::Price

#### field: input

Input token rate.

- type: `float`
- semantics: dollars per million input tokens
- code: groom/groom/prices.py::Price.input

#### field: output

Output token rate.

- type: `float`
- semantics: dollars per million output tokens
- code: groom/groom/prices.py::Price.output

#### field: cache_read

Cache read token rate.

- type: `float`
- semantics: dollars per million cache-hit tokens (derived from input rate at 0.1x multiplier, or overridden)
- code: groom/groom/prices.py::Price.cache_read

#### field: cache_write

Cache write token rate.

- type: `float`
- semantics: dollars per million cache-creation tokens (derived from input rate at 2.0x multiplier for hour-TTL, or overridden)
- code: groom/groom/prices.py::Price.cache_write

### prices_path

The path to the override file, resolving `$GROOM_PRICES` or the standard config directory.

- sig: `prices_path() -> Path`
- returns: path to `$GROOM_PRICES` if set, else `<config dir>/stablemate/prices.toml`; parent directories are not created
- code: groom/groom/prices.py::prices_path

### table

Built-in rates with the override file applied, cached for the process lifetime.

- sig: `table() -> dict[str, Price]`
- returns: a dict mapping normalized model id to [Price](#price); loaded on first call and kept in memory
- does: if the override file does not exist or is malformed, the warning is logged and the built-in table alone is returned
- code: groom/groom/prices.py::table

### reset

Drop the cached table so the next call re-reads the override file (tests).

- sig: `reset() -> None`
- code: groom/groom/prices.py::reset

### price_for

This model's rates, or None when nothing in the table names it.

- sig: `price_for(model: str) -> Price | None`
- returns: a [Price](#price) when the model is in the table after normalization, or None when the model is unpriced
- returns: when the input carries route segments — e.g. `openrouter/openai/gpt-5.6-luna` — progressively strips the first segment until a match is found, so a routed id's tail segment is the resolved model
- code: groom/groom/prices.py::price_for

Model normalization strips date suffixes (e.g., `claude-sonnet-5-20250929` becomes `claude-sonnet-5`), lowercases, and whitespace.

### estimate

What those tokens are worth at this model's rates, or None when it has none.

- sig: `estimate(model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None = None, cache_creation_tokens: int | None = None) -> float | None`
- returns: None if the model is unpriced
- returns: None if all token counts are None
- returns: estimated cost in USD, computed as `(input_tokens * rate.input + output_tokens * rate.output + cache_read_tokens * rate.cache_read + cache_creation_tokens * rate.cache_write) / 1_000_000`
- code: groom/groom/prices.py::estimate

When a turn reports some token classes but not others, only the reported classes are priced; absent counts are treated as 0, not unknown.

