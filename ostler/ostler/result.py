"""The value every ostler writer returns.

It lives in its own leaf module rather than in ``crud`` so that the writers can import each
other at module level: ``crud.delete_epic`` prunes the queue through ``todo``, and ``todo``
returns a ``Result``, which made the pair mutually importable only via a function-local
import. A dataclass with no ostler dependencies breaks that knot for good.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Result:
    ok: bool
    message: str
    paths: list[Path] = field(default_factory=list)
    entity_id: str = ""   # the allocated id, for create commands (consumed via --json)
