"""Orchestrate `ostler artifact scaffold|vet|list` invocations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .kinds import KINDS, get_kind


@dataclass
class ArtifactOutcome:
    kind: str
    path: str
    status: str  # "clean" | "problems" | "error"
    problems: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        out: dict = {"kind": self.kind, "path": self.path, "status": self.status}
        if self.problems:
            out["problems"] = self.problems
        if self.error:
            out["error"] = self.error
        return out


def _resolve_spec_dir(spec: Path, root: Path) -> Path:
    return spec if spec.is_absolute() else root / spec


def list_kinds() -> list[dict]:
    return [
        {"kind": k.name, "filename": k.filename, "description": k.description}
        for k in KINDS.values()
    ]


def scaffold(kind_name: str, spec: Path, root: Path, *, force: bool = False) -> ArtifactOutcome:
    kind = get_kind(kind_name)
    if kind is None:
        return ArtifactOutcome(kind_name, "", "error",
                               error=f"unknown artifact kind '{kind_name}' (known: {sorted(KINDS)})")
    spec_dir = _resolve_spec_dir(spec, root)
    target = spec_dir / kind.filename
    if target.exists() and not force:
        return ArtifactOutcome(kind_name, str(target), "error",
                               error=f"{target} already exists (pass --force to overwrite)")
    spec_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(kind.scaffold(), indent=2) + "\n", encoding="utf-8")
    return ArtifactOutcome(kind_name, str(target), "clean")


def vet(kind_name: str, spec: Path, root: Path) -> ArtifactOutcome:
    kind = get_kind(kind_name)
    if kind is None:
        return ArtifactOutcome(kind_name, "", "error",
                               error=f"unknown artifact kind '{kind_name}' (known: {sorted(KINDS)})")
    spec_dir = _resolve_spec_dir(spec, root)
    target = spec_dir / kind.filename
    if not target.is_file():
        return ArtifactOutcome(kind_name, str(target), "error",
                               error=f"{target} does not exist — scaffold it first")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — any parse error is a vet problem
        return ArtifactOutcome(kind_name, str(target), "problems",
                               problems=[f"not valid JSON: {exc}"])
    problems = kind.vet(data, spec_dir, root)
    return ArtifactOutcome(kind_name, str(target),
                           "problems" if problems else "clean", problems=problems)
