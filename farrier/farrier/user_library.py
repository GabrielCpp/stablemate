"""The ``[user_library.*]`` tables — what a user installs for every project at once.

Repo scope reads ``agents.yml``, which lives in the repo it configures. User scope has
no repo to hold a file, so the selection lives in the stablemate config
(``~/.config/stablemate/config.toml``) beside the other machine-wide settings.

This module only reads and validates those tables. Rendering them is
``outputs.render_user_expected``, which is the user-scope sibling of the repo-scope
renderer and shares every step of it below the selection.
"""
from __future__ import annotations

from typing import Any

#: The harnesses a user-scope table may name. Not read from anywhere else: a table
#: named for a harness farrier has no adapter for selects files nothing installs, and
#: silently rendering nothing is the failure mode this list exists to make loud.
HARNESSES = ("claude", "codex", "copilot")

#: The config table. ``[user_library.template]`` sits inside it alongside the per-
#: harness tables and is not one of them.
USER_LIBRARY_KEY = "user_library"
TEMPLATE_KEY = "template"


def _table(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit(f"error: [{name}] must be a TOML table")
    return value


def user_library_tables(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The per-harness selections, in :data:`HARNESSES` order, empty ones dropped.

    A misspelled harness is an error rather than an ignored table. The whole surface of
    a user-scope install is which harnesses were named, so a table nothing reads
    installs nothing and reports success — and the operator's evidence that it worked
    is the skills they cannot find afterwards.
    """
    table = _table(config.get(USER_LIBRARY_KEY) or {}, USER_LIBRARY_KEY)
    unknown = [
        key for key in table if key not in HARNESSES and key != TEMPLATE_KEY
    ]
    if unknown:
        raise SystemExit(
            "error: unknown user_library table(s): "
            + ", ".join(f"[{USER_LIBRARY_KEY}.{key}]" for key in sorted(unknown))
            + ". Known harnesses: "
            + ", ".join(HARNESSES)
            + f"; shared template values go in [{USER_LIBRARY_KEY}.{TEMPLATE_KEY}]."
        )
    return {
        name: _table(table[name], f"{USER_LIBRARY_KEY}.{name}")
        for name in HARNESSES
        if table.get(name)
    }


def user_template_values(config: dict[str, Any]) -> dict[str, Any]:
    """``[user_library.template]`` — one table, shared by every harness.

    Not per-harness: a template value describes the machine or the person, not the CLI
    reading the skill, and duplicating it per table is three places for the same value
    to disagree.
    """
    table = _table(config.get(USER_LIBRARY_KEY) or {}, USER_LIBRARY_KEY)
    return dict(_table(table.get(TEMPLATE_KEY) or {}, f"{USER_LIBRARY_KEY}.{TEMPLATE_KEY}"))
