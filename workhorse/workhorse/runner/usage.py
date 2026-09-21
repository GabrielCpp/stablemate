"""Normalize each harness's token/cost reporting onto one canonical shape."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_ALIASES: dict[str, tuple[str, ...]] = {
    "input_tokens": ("input_tokens", "input", "prompt_tokens", "inputTokens"),
    "output_tokens": ("output_tokens", "output", "completion_tokens", "outputTokens"),
    "cache_read_input_tokens": (
        "cache_read_input_tokens",
        "cached_input_tokens",
        "cache_read_tokens",
        "cached_tokens",
        "cacheReadTokens",
    ),
    "cache_creation_input_tokens": (
        "cache_creation_input_tokens",
        "cache_creation_tokens",
        "cache_write_tokens",
        "cacheWriteTokens",
    ),
    "reasoning_output_tokens": (
        "reasoning_output_tokens",
        "reasoning_tokens",
        "reasoning",
    ),
}
_CACHE_SUBKEYS = {"read": "cache_read_input_tokens", "write": "cache_creation_input_tokens"}
_COST_KEYS = ("total_cost_usd", "cost_usd", "total_cost", "cost", "totalCost")
_USAGE_CONTAINERS = ("usage", "tokens", "token_usage", "usageMetadata")
_TOKEN_MARKERS = frozenset(
    alias for aliases in _ALIASES.values() for alias in aliases
) | {"total"}
_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "reasoning_output_tokens",
)


def _add(total: int | None, part: int | None) -> int | None:
    """Fold one reported count into a running total, keeping "not reported" distinct from a reported zero: absent + absent stays absent."""
    if part is None:
        return total
    return (total or 0) + part


@dataclass(frozen=True, slots=True)
class TurnUsage:
    """What one turn consumed, in the canonical (Claude) key names."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    total_cost_usd: float | None = None
    duration_ms: int | None = None

    def token_counts(self) -> dict[str, int]:
        """The token fields this turn actually reported, canonical name → count."""
        return {
            name: count
            for name in _TOKEN_FIELDS
            if (count := getattr(self, name)) is not None
        }

    @property
    def generated_tokens(self) -> int | None:
        """Every token the model *produced* this turn — the answer and the thinking it did to get there — or ``None`` when the harness reported neither."""
        if self.output_tokens is None and self.reasoning_output_tokens is None:
            return None
        return (self.output_tokens or 0) + (self.reasoning_output_tokens or 0)

    @property
    def is_empty(self) -> bool:
        """True when the turn reported neither tokens nor money, i.e."""
        return not self.token_counts() and self.total_cost_usd is None

    def merge(self, part: TurnUsage) -> TurnUsage:
        """Fold one report into a running per-turn total, as a new value."""
        if part.is_empty:
            return self
        return TurnUsage(
            input_tokens=_add(self.input_tokens, part.input_tokens),
            output_tokens=_add(self.output_tokens, part.output_tokens),
            cache_read_input_tokens=_add(
                self.cache_read_input_tokens, part.cache_read_input_tokens
            ),
            cache_creation_input_tokens=_add(
                self.cache_creation_input_tokens, part.cache_creation_input_tokens
            ),
            reasoning_output_tokens=_add(
                self.reasoning_output_tokens, part.reasoning_output_tokens
            ),
            total_cost_usd=(
                self.total_cost_usd
                if part.total_cost_usd is None
                else (self.total_cost_usd or 0.0) + part.total_cost_usd
            ),
            duration_ms=(
                self.duration_ms if part.duration_ms is None else part.duration_ms
            ),
        )


def _as_int(value: Any) -> int | None:
    """Coerce a reported count to int, or None if it is not a usable number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and value != int(value):
        return None
    return int(value)


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _read_tokens(source: dict[str, Any]) -> dict[str, int]:
    """Pull canonical counts out of one token-shaped dict."""
    out: dict[str, int] = {}
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            count = _as_int(source.get(alias))
            if count is not None:
                out[canonical] = count
                break
    cache = source.get("cache")
    if isinstance(cache, dict):
        for subkey, canonical in _CACHE_SUBKEYS.items():
            count = _as_int(cache.get(subkey))
            if count is not None:
                out[canonical] = count
    return out


def _find_tokens(obj: Any, depth: int = 0) -> dict[str, int]:
    """Search ``obj`` for the token-shaped dict, preferring a named container."""
    if depth > 4 or not isinstance(obj, dict):
        return {}
    for key in _USAGE_CONTAINERS:
        nested = obj.get(key)
        if isinstance(nested, dict):
            found = _read_tokens(nested)
            if found:
                return found
    if _TOKEN_MARKERS & obj.keys():
        found = _read_tokens(obj)
        if found:
            return found
    for value in obj.values():
        if isinstance(value, dict):
            found = _find_tokens(value, depth + 1)
            if found:
                return found
    return {}


def _find_cost(obj: Any, depth: int = 0) -> float | None:
    if depth > 4 or not isinstance(obj, dict):
        return None
    for key in _COST_KEYS:
        cost = _as_float(obj.get(key))
        if cost is not None:
            return cost
    for value in obj.values():
        if isinstance(value, dict):
            cost = _find_cost(value, depth + 1)
            if cost is not None:
                return cost
    return None


def normalize(event: dict[str, Any]) -> TurnUsage:
    """Map one backend's completion event onto the canonical ``TurnUsage``."""
    return TurnUsage(
        **_find_tokens(event),
        total_cost_usd=_find_cost(event),
        duration_ms=_as_int(event.get("duration_ms") or event.get("durationMs")),
    )
