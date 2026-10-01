"""The dry-run-by-default file writes `ostler vet --write` applies, text or binary."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VetFileWrite:
    path: Path
    content: str | bytes

    def diff(self) -> str:
        if isinstance(self.content, bytes):
            if self.path.is_file() and self.path.read_bytes() == self.content:
                return ""
            return f"write {self.path.as_posix()} ({len(self.content)} bytes)\n"
        old = self.path.read_text(encoding="utf-8") if self.path.is_file() else ""
        if old == self.content:
            return ""
        rel = self.path.as_posix()
        return "".join(difflib.unified_diff(
            old.splitlines(keepends=True), self.content.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}",
        ))

    def apply(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(self.content, bytes):
            self.path.write_bytes(self.content)
        else:
            self.path.write_text(self.content, encoding="utf-8")


@dataclass
class VetPlan:
    writes: list[VetFileWrite]
    error: str = ""

    def render(self) -> str:
        if self.error:
            return f"error: {self.error}"
        parts = [d for w in self.writes if (d := w.diff())]
        return "".join(parts) if parts else "no changes"

    def apply(self) -> None:
        for w in self.writes:
            w.apply()
