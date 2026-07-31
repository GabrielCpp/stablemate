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
    # The name the writer actually used, when it may differ from the one asked for: an epic
    # is created into a numbered directory (`0001-checkout-flow`), and the caller that has
    # to write files under it needs the name that exists, not the slug it proposed.
    entity_name: str = ""
