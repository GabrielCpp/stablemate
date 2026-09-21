"""One error shape for every "agents.yml names something the library does not have"."""
from __future__ import annotations

import difflib

from farrier.layers import searched_layers

_SIMILARITY_CUTOFF = 0.6
_MAX_SUGGESTIONS = 3
_RUNNER_UP_MARGIN = 0.06
_MAX_LISTED = 40


def _normalize(name: str) -> str:
    """Case- and separator-insensitive form: ``Demo/React_Router`` → ``demoreactrouter``."""
    return "".join(char for char in name.lower() if char.isalnum())


def suggestions(name: str, available: list[str]) -> list[str]:
    """Close matches for ``name``, best first."""
    target_norm = _normalize(name)
    target_chars = sorted(target_norm)
    exact: list[str] = []
    for candidate in available:
        candidate_norm = _normalize(candidate)
        if candidate_norm == target_norm or sorted(candidate_norm) == target_chars:
            exact.append(candidate)
    if exact:
        return exact[:_MAX_SUGGESTIONS]

    scored = [
        (difflib.SequenceMatcher(None, name, candidate).ratio(), candidate)
        for candidate in available
    ]
    scored = sorted(
        ((ratio, name_) for ratio, name_ in scored if ratio >= _SIMILARITY_CUTOFF),
        key=lambda pair: (-pair[0], pair[1]),
    )
    if not scored:
        return []
    best = scored[0][0]
    return [
        candidate
        for ratio, candidate in scored[:_MAX_SUGGESTIONS]
        if best - ratio <= _RUNNER_UP_MARGIN
    ]


def _available_block(kind: str, available: list[str]) -> str:
    if not available:
        return (
            f"No {kind} are available from the current library layers at all — which usually "
            f"means the layer holding them is not configured, rather than that you named the "
            f"wrong one."
        )
    listed = sorted(available)
    lines = [f"Available {kind} ({len(listed)}):"]
    lines += [f"  - {name}" for name in listed[:_MAX_LISTED]]
    if len(listed) > _MAX_LISTED:
        lines.append(f"  … and {len(listed) - _MAX_LISTED} more")
    return "\n".join(lines)


def unknown_selection_error(
    kind: str,
    missing: list[str],
    available: list[str],
    *,
    config_key: str = "",
    extra: str = "",
) -> str:
    """The full message for one or more unresolvable selection entries."""
    key = config_key or kind
    singular = kind[:-1] if kind.endswith("s") else kind
    label = f"unknown {singular if len(missing) == 1 else kind}"

    lines = [f"error: {label} in agents.yml `{key}:`"]
    for name in sorted(missing):
        lines.append(f"  - {name}")
        close = suggestions(name, available)
        if close:
            lines.append(f"      did you mean: {', '.join(close)}?")

    lines += ["", _available_block(kind, available)]
    lines += ["", "Searched these library layers:", searched_layers()]
    if extra:
        lines += ["", extra]
    lines += [
        "",
        f"Fix the name in agents.yml, or remove it from `{key}:`.",
        "If it lives in a private overlay library farrier cannot see, point farrier at it:",
        "    farrier config set-library <path-to-your-library>",
    ]
    return "\n".join(lines)
