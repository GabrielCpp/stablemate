"""The one problem `ostler doctor` reports, shared by every module that checks a book."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    epic: str = ""
    ref: str = ""
    path: str = ""
    line: int = 0
    suggestion: str = ""
    fixable: bool = False
    node: str = ""
    related: list[str] = field(default_factory=list)
