"""The `template:` table of `agents.yml`, with the older `vars:` merged in."""
from __future__ import annotations

from typing import Any


from farrier.manifest import ConfigLike, as_manifest


def collect_template_values(config: ConfigLike) -> dict[str, Any]:
    """The values library templates render with."""
    return as_manifest(config).template.mapping()
