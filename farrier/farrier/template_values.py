"""The `vars:` / `template:` mapping from `agents.yml`."""
from __future__ import annotations

from typing import Any


def collect_template_values(config: dict[str, Any]) -> dict[str, Any]:
    """Merge `vars:` then `template:` into one mapping, later keys winning."""
    values: dict[str, Any] = {}
    for key in ["vars", "template"]:
        configured = config.get(key) or {}
        if not isinstance(configured, dict):
            raise SystemExit(f"{key} must be a YAML mapping when present")
        values.update(configured)
    return values
