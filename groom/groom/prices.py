"""What a turn's tokens would have cost, for the harnesses that do not say.

Half the turns in a busy store report no money. A subscription CLI reports a literal
``$0`` over tens of millions of tokens; an older span carries no usage at all; a harness
behind a proxy never sees a price. `groom cost` is honest about that — absent is NULL and
a reported zero stays zero — but honesty alone does not answer the question anyone
actually has, which is *which of these two loops burned more*.

So this module prices tokens instead of trusting the report: a small table of published
per-million rates, and one estimate derived from the four token counts every harness does
report. The estimate is kept in its own column (`est_cost_usd`) and is never summed with
`total_cost_usd`. They are different claims — one is what a vendor billed, the other is
what a rate card says the tokens are worth — and a total mixing them is a number nobody
can act on.

**An unknown model is not priced.** No family guessing, no averaging of neighbours: a
model absent from the table yields ``None`` and is counted as unpriceable, so the fraction
of a report that rests on an estimate is always visible. Adding one is a line in
``~/.config/stablemate/prices.toml`` (``$GROOM_PRICES`` points elsewhere):

```toml
[models."openai/gpt-5.6-sol"]
input = 1.25          # $ per million input tokens
output = 10.0
cache_read = 0.125    # optional; defaults to 0.1 x input
cache_write = 2.5     # optional; defaults to 2.0 x input
```

The cache defaults are the multipliers Anthropic publishes — reads at a tenth of the
input rate, writes at 1.25x for the five-minute TTL and 2x for the hour — and this module
takes the *hour*, because a run that keeps one context alive across a long turn is
exactly what it is used to price. Checked against 528 turns in a live store that reported
a real price: median per-turn estimate 0.99x the billed amount, aggregate 0.82x — the tail
it misses is turns that mixed both TTLs and turns billed at the long-context premium. That
is the accuracy on offer, and it is the reason the column stays separate.
"""

from __future__ import annotations

import logging
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir

logger = logging.getLogger(__name__)

#: Cache reads bill at a fraction of the input rate; cache writes at a multiple of it.
#: Both are ratios rather than table columns because that is how they are published —
#: a vendor that changes the input price changes these with it.
CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 2.0

#: Where an operator extends or corrects the table.
PRICES_FILE_ENV = "GROOM_PRICES"

#: A dated model id — `claude-sonnet-4-5-20250929` — prices as its undated form.
_DATE_SUFFIX = re.compile(r"-\d{8}$")


@dataclass(frozen=True, slots=True)
class Price:
    """Dollars per million tokens, one rate per token class."""

    input: float
    output: float
    cache_read: float
    cache_write: float


def _rates(input_rate: float, output_rate: float) -> Price:
    """A row from the two rates a vendor publishes, cache derived from the multipliers."""
    return Price(
        input=input_rate,
        output=output_rate,
        cache_read=input_rate * CACHE_READ_MULTIPLIER,
        cache_write=input_rate * CACHE_WRITE_MULTIPLIER,
    )


#: Anthropic first-party rates, in dollars per million tokens. Only the models this
#: repo's own runs use — the table is a convenience for the common case, not an attempt
#: at a catalogue, and everything else belongs in the override file where it can be kept
#: current by whoever is paying the bill.
DEFAULT_PRICES: dict[str, Price] = {
    "claude-fable-5": _rates(10.00, 50.00),
    "claude-opus-5": _rates(5.00, 25.00),
    "claude-opus-4-8": _rates(5.00, 25.00),
    "claude-opus-4-7": _rates(5.00, 25.00),
    "claude-opus-4-6": _rates(5.00, 25.00),
    "claude-opus-4-5": _rates(5.00, 25.00),
    "claude-opus-4-1": _rates(15.00, 75.00),
    "claude-opus-4-0": _rates(15.00, 75.00),
    "claude-sonnet-5": _rates(3.00, 15.00),
    "claude-sonnet-4-6": _rates(3.00, 15.00),
    "claude-sonnet-4-5": _rates(3.00, 15.00),
    "claude-sonnet-4-0": _rates(3.00, 15.00),
    "claude-haiku-4-5": _rates(1.00, 5.00),
}

_table: dict[str, Price] | None = None


def prices_path() -> Path:
    """The override file: ``$GROOM_PRICES``, else ``<config dir>/stablemate/prices.toml``."""
    raw = os.environ.get(PRICES_FILE_ENV)
    if raw:
        return Path(raw).expanduser()
    return Path(user_config_dir("stablemate")) / "prices.toml"


def _overrides() -> dict[str, Price]:
    """What the operator's file adds or corrects; empty when there is none.

    A malformed file is logged and ignored rather than raised: pricing is a convenience
    over telemetry, and a typo in a rate card must not take down the dashboard that
    reads it.
    """
    path = prices_path()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("price overrides unreadable, ignoring: %s", path)
        return {}
    found: dict[str, Price] = {}
    for model, entry in (raw.get("models") or {}).items():
        try:
            input_rate, output_rate = float(entry["input"]), float(entry["output"])
        except (TypeError, ValueError, KeyError):
            logger.warning("price override for %s needs input and output rates", model)
            continue
        base = _rates(input_rate, output_rate)
        found[_normalize(str(model))] = Price(
            input=base.input,
            output=base.output,
            cache_read=float(entry.get("cache_read", base.cache_read)),
            cache_write=float(entry.get("cache_write", base.cache_write)),
        )
    return found


def table() -> dict[str, Price]:
    """Built-in rates with the override file applied, read once per process."""
    global _table
    if _table is None:
        _table = {**DEFAULT_PRICES, **_overrides()}
    return _table


def reset() -> None:
    """Drop the cached table so the next call re-reads the override file (tests)."""
    global _table
    _table = None


def _normalize(model: str) -> str:
    return _DATE_SUFFIX.sub("", model.strip().lower())


def price_for(model: str) -> Price | None:
    """This model's rates, or None when nothing in the table names it.

    A routed id carries its route — ``openrouter/openai/gpt-5.6-luna`` — so the lookup
    drops leading path segments one at a time. That is a narrowing of the same name, not
    a guess at a different model: the tail of a route is the model the provider ran. A
    name that survives to nothing stays unpriced.
    """
    rates = table()
    name = _normalize(model)
    while name:
        found = rates.get(name)
        if found is not None:
            return found
        _route, sep, tail = name.partition("/")
        if not sep:
            return None
        name = tail
    return None


def estimate(
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_tokens: int | None = None,
    cache_creation_tokens: int | None = None,
) -> float | None:
    """What those tokens are worth at this model's rates, or None when it has none.

    None also when the turn reported no tokens at all: an estimate of ``0.0`` over an
    unknown number of tokens is the exact false zero this module exists to distinguish
    from a real one. A turn reporting some classes and not others prices the ones it
    reported — an absent cache count means no cache was used often enough that treating
    it as unknown would refuse to price most of the store.
    """
    rates = price_for(model)
    if rates is None:
        return None
    counts = (input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)
    if all(count is None for count in counts):
        return None
    per = (rates.input, rates.output, rates.cache_read, rates.cache_write)
    return sum(rate * (count or 0) for rate, count in zip(per, counts, strict=True)) / 1e6
