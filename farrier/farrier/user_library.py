"""The ``[user_library.*]`` tables — what a user installs for every project at once."""
from __future__ import annotations

from typing import Any

HARNESSES = ("claude", "codex", "copilot")

USER_LIBRARY_KEY = "user_library"
TEMPLATE_KEY = "template"


def _table(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit(f"error: [{name}] must be a TOML table")
    return value


def user_library_tables(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The per-harness selections, in :data:`HARNESSES` order, empty ones dropped."""
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
    """``[user_library.template]`` — one table, shared by every harness."""
    table = _table(config.get(USER_LIBRARY_KEY) or {}, USER_LIBRARY_KEY)
    return dict(_table(table.get(TEMPLATE_KEY) or {}, f"{USER_LIBRARY_KEY}.{TEMPLATE_KEY}"))
