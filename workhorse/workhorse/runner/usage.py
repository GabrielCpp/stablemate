"""Normalize each harness's token/cost reporting onto one canonical shape.

Every agent CLI reports what a turn consumed, and every one of them spells it
differently. Until this module existed only Claude's ``result`` event was parsed,
so a telemetry store could compare latency across backends but not tokens and not
money — 21% of recorded turns carried no usage at all, and all of them were the
non-Claude ones. Comparing two model classes on cost is exactly the question that
gap made unanswerable.

The canonical key names are **Claude's**, deliberately: spans carrying them are
already in the store, and renaming would strand that history behind a query the
analysis has to special-case.

Verified event shapes (captured from the installed CLIs, 2026-07-27):

- claude   ``{"type":"result", "usage":{"input_tokens","output_tokens",
           "cache_read_input_tokens","cache_creation_input_tokens"},
           "total_cost_usd", "duration_ms"}``
- codex    ``{"type":"turn.completed", "usage":{"input_tokens",
           "cached_input_tokens","output_tokens","reasoning_output_tokens"}}``
           — no cost (subscription auth)
- opencode ``{"type":"step_finish", "part":{"tokens":{"input","output",
           "reasoning","cache":{"read","write"}}, "cost":0}}`` — one event per
           *step*, so a multi-tool turn emits several and they must be summed
- copilot  ``{"type":"result", "sessionId", "exitCode", "usage":{
           "premiumRequests","totalApiDurationMs","sessionDurationMs",
           "codeChanges":{...}}}`` (CLI 1.0.65, captured 2026-08-05) — **no token
           counts and no currency of any kind.** Copilot bills in *premium
           requests*, so there is nothing here to map onto the token fields, and a
           copilot turn reports empty: it is routed past ``finalize_turn``'s
           ``is_empty`` guard and carries only the engine's own duration.

           The `codeChanges` sub-dict is why the recursive search is guarded rather
           than merely bounded: it is a nested dict of integers sitting directly
           beside `usage`, and an unguarded search would invent token counts out of
           a lines-changed tally.

That fallback is the reason this is tolerant rather than a per-backend switch: an
unrecognized shape costs a missing attribute, never an exception. A turn that
reports nothing still gets ``duration_ms`` stamped by the engine itself (see
``otel.turn_end``), so latency coverage is total regardless of harness.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Canonical name → the spellings seen in the wild. Order matters only in that the
# first alias present wins; the lists are disjoint per canonical key, so it does
# not matter in practice.
_ALIASES: dict[str, tuple[str, ...]] = {
    "input_tokens": ("input_tokens", "input", "prompt_tokens"),
    "output_tokens": ("output_tokens", "output", "completion_tokens"),
    "cache_read_input_tokens": (
        "cache_read_input_tokens",
        "cached_input_tokens",
        "cache_read_tokens",
        "cached_tokens",
    ),
    "cache_creation_input_tokens": (
        "cache_creation_input_tokens",
        "cache_creation_tokens",
        "cache_write_tokens",
    ),
    "reasoning_output_tokens": (
        "reasoning_output_tokens",
        "reasoning_tokens",
        "reasoning",
    ),
}
# Nested under a `cache: {read, write}` sub-dict (opencode) rather than flattened
# into the token dict itself.
_CACHE_SUBKEYS = {"read": "cache_read_input_tokens", "write": "cache_creation_input_tokens"}
_COST_KEYS = ("total_cost_usd", "cost_usd", "total_cost", "cost")
# Keys whose value is the dict actually holding the counts.
_USAGE_CONTAINERS = ("usage", "tokens", "token_usage", "usageMetadata")
# A dict is "token-shaped" if it names at least one of these. Guards the recursive
# fallback from latching onto some unrelated dict that happens to have an `input`.
_TOKEN_MARKERS = frozenset(
    alias for aliases in _ALIASES.values() for alias in aliases
) | {"total"}
# The canonical token fields, in the order telemetry stamps them onto a span.
# Same names as ``_ALIASES``'s keys and ``_CACHE_SUBKEYS``'s values, which is what
# lets an extracted count dict be splatted straight into ``TurnUsage``.
_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "reasoning_output_tokens",
)


def _add(total: int | None, part: int | None) -> int | None:
    """Fold one reported count into a running total, keeping "not reported"
    distinct from a reported zero: absent + absent stays absent."""
    if part is None:
        return total
    return (total or 0) + part


@dataclass(frozen=True, slots=True)
class TurnUsage:
    """What one turn consumed, in the canonical (Claude) key names.

    Every field is optional and ``None`` means *this harness does not say* —
    deliberately distinct from a reported zero. A real ``0.0`` (an opencode
    subscription turn) means "this cost nothing"; a missing value means "not
    measured", and averaging the two together would understate spend. The same
    reasoning applies per token field: ``reasoning_output_tokens`` is reported by
    codex and opencode and absent from Claude's ``result`` event, so it is left
    off the span rather than zeroed.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    total_cost_usd: float | None = None
    duration_ms: int | None = None

    def token_counts(self) -> dict[str, int]:
        """The token fields this turn actually reported, canonical name → count.
        A field the harness did not report is absent here, never zero."""
        return {
            name: count
            for name in _TOKEN_FIELDS
            if (count := getattr(self, name)) is not None
        }

    @property
    def is_empty(self) -> bool:
        """True when the turn reported neither tokens nor money, i.e. there is
        nothing to fold and nothing worth stamping. Duration alone does not
        count: the engine measures that itself (``otel.turn_end``)."""
        return not self.token_counts() and self.total_cost_usd is None

    def merge(self, part: TurnUsage) -> TurnUsage:
        """Fold one report into a running per-turn total, as a new value.

        Needed because opencode reports per *step*: a turn that calls three tools
        emits three ``step_finish`` events, and only their sum is the turn's cost.
        Backends that report once per turn merge a single value and are
        unaffected. Counts and cost add; duration is a span of time, not a
        quantity, so the last report wins rather than summing into nonsense. An
        empty ``part`` folds to a no-op, leaving the total (and its absences)
        alone.
        """
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
    """Coerce a reported count to int, or None if it is not a usable number.

    Booleans are rejected explicitly: ``isinstance(True, int)`` is True in Python,
    and a stray ``{"cache": {"read": true}}`` would otherwise land in the store as
    a token count of 1.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
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
    """Search ``obj`` for the token-shaped dict, preferring a named container.

    Depth is bounded because this runs on every event of every turn: an unbounded
    walk over a large tool-result payload would be real per-event cost for a
    backend whose shape we already know.
    """
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
    """Map one backend's completion event onto the canonical ``TurnUsage``.

    The event stays a raw ``dict``: it is a foreign, version-drifting payload we
    do not own, so it is read tolerantly and whatever is unrecognized is shrugged
    off. The typed boundary is the value this returns, not the wire shape it came
    from. Anything the event did not report stays ``None`` — the span then goes
    without rather than carrying a fabricated zero.
    """
    return TurnUsage(
        **_find_tokens(event),
        total_cost_usd=_find_cost(event),
        duration_ms=_as_int(event.get("duration_ms")),
    )


# Aider streams plain text and ends with a line like:
#   Tokens: 3.4k sent, 213 received. Cost: $0.0123 message, $0.05 session.
# Unverified against a live run (it needs a provider key), so it is deliberately a
# best-effort regex over the transcript rather than a parse: no match simply means
# no usage attributes, exactly as if the CLI had said nothing.
_AIDER_TOKENS = re.compile(
    r"Tokens:\s*([\d.]+)([kKmM]?)\s*sent,\s*([\d.]+)([kKmM]?)\s*received", re.I
)
_AIDER_COST = re.compile(r"Cost:\s*\$([\d.]+)\s*message", re.I)
_SUFFIX = {"": 1, "k": 1_000, "m": 1_000_000}


def from_text(transcript: str | None) -> TurnUsage:
    """Best-effort usage for a text-streaming backend (aider). Last report wins —
    a multi-step turn reprints the line, and the final one is the turn's total.

    ``None`` is accepted, and is not the same question as "did it report usage": a
    turn whose transcript was never captured has no usage either, and the caller on
    the hot path of every stream should not have to say so twice."""
    counts: dict[str, int] = {}
    matches = _AIDER_TOKENS.findall(transcript or "")
    if matches:
        sent, sent_unit, received, received_unit = matches[-1]
        try:
            counts = {
                "input_tokens": int(float(sent) * _SUFFIX[sent_unit.lower()]),
                "output_tokens": int(float(received) * _SUFFIX[received_unit.lower()]),
            }
        except (ValueError, KeyError):
            counts = {}
    cost: float | None = None
    costs = _AIDER_COST.findall(transcript or "")
    if costs:
        try:
            cost = float(costs[-1])
        except ValueError:
            cost = None
    return TurnUsage(**counts, total_cost_usd=cost)
