"""One error shape for every "agents.yml names something the library does not have".

Five selection keys can name a missing thing — ``packs``, ``workflows``, ``skills``,
``prompts``, ``roots`` — and they used to fail in four different ways, two of them silently.
Every one of them is the same operator mistake and deserves the same answer, so they share one
formatter here.

An error is verbose because of what the operator is actually stuck on. Knowing *that*
``go-srvice`` is unknown does not help; the questions are "what did I mean", "what is
available", "where did you look", and "is it missing or just in a library you cannot see".
The last one matters most in this codebase: skills and packs live in a private overlay, so a
name that is genuinely correct still resolves to nothing on a machine with no overlay
configured. A bare "unknown pack" reads as a typo and sends people hunting for a
misspelling that is not there.

Layout::

    error: unknown skill in agents.yml `skills:`
      - demo/go-srvice
          did you mean: demo/go-service?

    Available skills (3):
      - demo/go-service
      - demo/react-router
      - demo/flutter

    Searched these library layers:
      - /path/to/overlay
      - base-library (base)

    Fix the name in agents.yml, or remove it from `skills:`.
    If it lives in a private overlay library farrier cannot see, point farrier at it:
        farrier config set-library <path-to-your-library>
"""
from __future__ import annotations

import difflib

from farrier.layers import searched_layers

# Enough to catch a transposition or a dropped letter, tight enough that an unrelated name
# is not offered as a suggestion — a wrong "did you mean" is worse than none, because it
# sends the operator to edit a line that was never the problem.
_SIMILARITY_CUTOFF = 0.6
_MAX_SUGGESTIONS = 3
# How far below the best match a runner-up may score and still be worth showing. Tight,
# because the value of a suggestion list collapses once it contains an obviously wrong entry.
_RUNNER_UP_MARGIN = 0.06
# Above this, printing the full catalog buries the error it is meant to explain.
_MAX_LISTED = 40


def _normalize(name: str) -> str:
    """Case- and separator-insensitive form: ``Demo/React_Router`` → ``demoreactrouter``."""
    return "".join(char for char in name.lower() if char.isalnum())


def suggestions(name: str, available: list[str]) -> list[str]:
    """Close matches for ``name``, best first. Empty when nothing is close enough.

    Two passes, because ``difflib`` alone is weak exactly where typos cluster. Its ratio is
    length-normalized, so a transposition in a short name scores far lower than intuition
    suggests — ``og`` vs ``go`` is 0.5, under any cutoff loose enough to be safe on long
    names. Anagram equality catches that class exactly (transpositions preserve characters)
    and costs nothing, so it runs first and difflib fills in the rest.
    """
    target_norm = _normalize(name)
    target_chars = sorted(target_norm)
    exact: list[str] = []
    for candidate in available:
        candidate_norm = _normalize(candidate)
        # Same characters, different order (or just different case/separators) — a typo,
        # not a coincidence. A match here is certain enough that fuzzy runners-up would
        # only dilute it.
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
    # Keep only genuinely competitive matches. A shared namespace prefix
    # ("stablemate/stablemate-…") lifts every sibling over the cutoff, so a plain top-N
    # would bury the one right answer under two near-ties that are not close at all.
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
    """The full message for one or more unresolvable selection entries.

    ``kind`` is the plural noun ("skills", "packs"); ``config_key`` is the agents.yml key to
    point at, defaulting to ``kind``. ``extra`` appends a key-specific note.
    """
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
