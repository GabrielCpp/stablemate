"""The value every ostler writer returns."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Result:
    ok: bool
    message: str
    paths: list[Path] = field(default_factory=list)
    entity_id: str = ""
    entity_name: str = ""
