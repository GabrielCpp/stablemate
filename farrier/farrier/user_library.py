"""The ``[user_library.*]`` tables — what a user installs for every project at once."""
from __future__ import annotations

from typing import Any

from farrier._vendor.stablemate_core.config import config_path
from farrier._vendor.stablemate_core.harness import home_harnesses
from farrier._vendor.stablemate_core.schema import HomeConfig, Selection

USER_LIBRARY_KEY = "user_library"
TEMPLATE_KEY = "template"


def user_library_tables(home: HomeConfig) -> dict[str, Selection]:
    """The per-harness selections, in registry order, empty ones dropped."""
    table = home.user_library
    if table is None:
        return {}
    unknown = list(table.model_extra or {})
    if unknown:
        raise SystemExit(
            "error: unknown user_library table(s): "
            + ", ".join(f"[{USER_LIBRARY_KEY}.{key}]" for key in sorted(unknown))
            + ". Known harnesses: "
            + ", ".join(spec.name for spec in home_harnesses())
            + f"; shared template values go in [{USER_LIBRARY_KEY}.{TEMPLATE_KEY}]."
        )
    tables: dict[str, Selection] = {}
    for spec in home_harnesses():
        name = spec.name
        selection: Selection | None = getattr(table, name)
        if selection is not None and (selection.model_fields_set or selection.model_extra):
            tables[name] = selection
    return tables


def user_template_values(home: HomeConfig) -> dict[str, Any]:
    """``[user_library.template]`` — one table, shared by every harness."""
    return {} if home.user_library is None else dict(home.user_library.template)


def user_library_origin(harness: str) -> str:
    """Where a user-library selection is written, for the errors that name it."""
    return f"{config_path()} [{USER_LIBRARY_KEY}.{harness}]"
