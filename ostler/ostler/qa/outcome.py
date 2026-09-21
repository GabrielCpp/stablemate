"""`QaOutcome` — the shared return shape for every `ostler qa` subcommand."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QaOutcome:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    status: str = ""

    def __post_init__(self) -> None:
        if not self.status:
            self.status = "passed" if self.ok else "failed"
        self.data.setdefault("status", self.status)
