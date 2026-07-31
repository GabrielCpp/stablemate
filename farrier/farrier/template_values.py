"""The `vars:` / `template:` mapping from `agents.yml`.

One reader, kept apart from `sources` (which selects *files*) because this
selects nothing: it collects the values the renderer exposes to a skill's or
prompt's Jinja, and the only thing it knows about the config is those two keys.
"""
from __future__ import annotations

from typing import Any


def collect_template_values(config: dict[str, Any]) -> dict[str, Any]:
    """Merge `vars:` then `template:` into one mapping, later keys winning.

    Both spellings are accepted for the same thing; `template:` is the older
    name. A non-mapping value is a config error rather than a silently ignored
    one, since the symptom otherwise is a skill rendering with an empty variable.
    """
    values: dict[str, Any] = {}
    for key in ["vars", "template"]:
        configured = config.get(key) or {}
        if not isinstance(configured, dict):
            raise SystemExit(f"{key} must be a YAML mapping when present")
        values.update(configured)
    return values
