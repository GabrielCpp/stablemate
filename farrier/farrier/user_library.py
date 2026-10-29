"""The ``[user_library.*]`` tables — what a user installs for every project at once."""
from __future__ import annotations

from typing import Any

from farrier._vendor.stablemate_core.schema import HomeConfig, Selection

HARNESSES = ("claude", "codex", "copilot")

USER_LIBRARY_KEY = "user_library"
TEMPLATE_KEY = "template"


def user_library_tables(home: HomeConfig) -> dict[str, Selection]:
    """The per-harness selections, in :data:`HARNESSES` order, empty ones dropped."""
    table = home.user_library
    if table is None:
        return {}
    unknown = list(table.model_extra or {})
    if unknown:
        raise SystemExit(
            "error: unknown user_library table(s): "
            + ", ".join(f"[{USER_LIBRARY_KEY}.{key}]" for key in sorted(unknown))
            + ". Known harnesses: "
            + ", ".join(HARNESSES)
            + f"; shared template values go in [{USER_LIBRARY_KEY}.{TEMPLATE_KEY}]."
        )
    tables: dict[str, Selection] = {}
    for name in HARNESSES:
        selection: Selection | None = getattr(table, name)
        if selection is not None and (selection.model_fields_set or selection.model_extra):
            tables[name] = selection
    return tables


def user_template_values(home: HomeConfig) -> dict[str, Any]:
    """``[user_library.template]`` — one table, shared by every harness."""
    return {} if home.user_library is None else dict(home.user_library.template)
