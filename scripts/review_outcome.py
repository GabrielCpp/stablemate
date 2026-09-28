"""What the stop hook answers with: a block, a give-up, a notice, or nothing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Block:
    reason: str

    def payload(self) -> dict[str, str]:
        return {"decision": "block", "reason": self.reason}


@dataclass(frozen=True)
class GiveUp:
    message: str

    def payload(self) -> dict[str, str]:
        return {"systemMessage": self.message}


@dataclass(frozen=True)
class Notice:
    message: str

    def payload(self) -> dict[str, str]:
        return {"systemMessage": self.message}


type Outcome = Block | GiveUp | Notice | None
