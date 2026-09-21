"""What a turn's tokens would have cost, for the harnesses that do not say."""

from __future__ import annotations

import logging
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir

logger = logging.getLogger(__name__)

CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 2.0

PRICES_FILE_ENV = "GROOM_PRICES"

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
    "gpt-5.5": Price(input=5.00, output=30.00, cache_read=0.50, cache_write=5.00),
    "gpt-5.6": Price(input=5.00, output=30.00, cache_read=0.50, cache_write=6.25),
    "gpt-5.6-sol": Price(input=5.00, output=30.00, cache_read=0.50, cache_write=6.25),
    "gpt-5.6-terra": Price(input=2.00, output=12.00, cache_read=0.20, cache_write=2.50),
    "gpt-5.6-terra-fast": Price(input=4.00, output=24.00, cache_read=0.40, cache_write=5.00),
    "gpt-5.6-luna": Price(input=0.20, output=1.20, cache_read=0.02, cache_write=0.25),
}

_table: dict[str, Price] | None = None


def prices_path() -> Path:
    """The override file: ``$GROOM_PRICES``, else ``<config dir>/stablemate/prices.toml``."""
    raw = os.environ.get(PRICES_FILE_ENV)
    if raw:
        return Path(raw).expanduser()
    return Path(user_config_dir("stablemate")) / "prices.toml"


def _overrides() -> dict[str, Price]:
    """What the operator's file adds or corrects; empty when there is none."""
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
    """This model's rates, or None when nothing in the table names it."""
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
    """What those tokens are worth at this model's rates, or None when it has none."""
    rates = price_for(model)
    if rates is None:
        return None
    counts = (input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)
    if all(count is None for count in counts):
        return None
    per = (rates.input, rates.output, rates.cache_read, rates.cache_write)
    return sum(rate * (count or 0) for rate, count in zip(per, counts, strict=True)) / 1e6
