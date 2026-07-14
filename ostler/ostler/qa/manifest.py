"""Current-run artifact manifest with content-addressed provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class RunManifest:
    def __init__(self, spec_dir: Path, run_id: str) -> None:
        self.spec_dir = spec_dir.resolve()
        self.path = self.spec_dir / "qa" / "run-manifest.json"
        self.data: dict[str, Any] = {
            "version": 1,
            "runId": run_id,
            "artifacts": [],
        }

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")

    def register(
        self,
        path: Path,
        *,
        kind: str,
        scenario: str = "",
        target: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self.spec_dir).as_posix()
        except ValueError as exc:
            raise ValueError(f"artifact escapes spec directory: {path}") from exc
        if not resolved.is_file():
            raise ValueError(f"artifact does not exist: {path}")
        entry: dict[str, Any] = {
            "path": relative,
            "kind": kind,
            "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
            "bytes": resolved.stat().st_size,
        }
        if scenario:
            entry["scenario"] = scenario
        if target:
            entry["target"] = target
        if metadata:
            entry.update(metadata)
        artifacts = self.data["artifacts"]
        artifacts[:] = [item for item in artifacts if item.get("path") != relative]
        artifacts.append(entry)
        artifacts.sort(key=lambda item: item["path"])
        self.write()
        return entry
