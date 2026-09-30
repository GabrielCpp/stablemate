"""The lap record: what each precondition built once in a lap, read back by every later scenario.

Each scenario runs in its own process, so a precondition built in one reaches the next only
through this record on disk. It holds the facts the precondition provides, or the fault that
stopped it, and lives no longer than the lap that made it.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Arranged:
    """One precondition as its first build in the lap left it: the facts it provides and the command's end, or the fault that stopped it."""

    facts: dict[str, str] = field(default_factory=dict)
    command: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    fault: dict[str, Any] | None = None
    error: str = ""


class LapRecord:
    """The preconditions one lap has built, one file per fixture and its arguments."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def built(self, name: str, args: Mapping[str, str]) -> Arranged | None:
        """How *name* with *args* was built earlier in this lap, or None when it was not."""
        path = self._path(name, args)
        if not path.is_file():
            return None
        return Arranged(**json.loads(path.read_text(encoding="utf-8")))

    def keep(self, name: str, args: Mapping[str, str], arranged: Arranged) -> None:
        """Record how *name* with *args* was built, so no later scenario of this lap builds it again."""
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(name, args)
        partial = path.with_suffix(".partial")
        partial.write_text(json.dumps(asdict(arranged)), encoding="utf-8")
        os.replace(partial, path)

    def _path(self, name: str, args: Mapping[str, str]) -> Path:
        key = json.dumps([name, sorted(args.items())])
        return self.directory / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.json"
