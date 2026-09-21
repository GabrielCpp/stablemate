"""`ostler freeze` / `unfreeze` — pin an approved entity as immutable ground truth."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ostler.model import Graph


def resolve_content(graph: Graph, ident: str) -> tuple[str, str] | None:
    """Return ``(kind, canonical_content)`` for a story slug or seed id, else None."""
    found = graph.find_story(ident)
    if found is not None:
        _, story = found
        if story.story_md and story.story_md.exists():
            return "story", story.story_md.read_text(encoding="utf-8")
        return "story", json.dumps(story.raw, sort_keys=True, ensure_ascii=False)
    for epic in graph.epics:
        for seed in epic.seeds:
            if seed.id == ident:
                return "seed", json.dumps(seed.raw, sort_keys=True, ensure_ascii=False)
    return None


def fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


@dataclass
class FreezePlan:
    action: str
    ident: str
    error: str = ""
    entry: dict = field(default_factory=dict)
    _ids_path: Path | None = None
    _ids: dict | None = None

    def render(self) -> str:
        if self.error:
            return f"error: {self.error}"
        if self.action == "freeze":
            return (f"freeze {self.entry['kind']} '{self.ident}'  "
                    f"hash={self.entry['hash']}  by={self.entry.get('approvedBy') or '?'}")
        return f"unfreeze '{self.ident}'"

    def apply(self) -> None:
        if self.error or self._ids is None or self._ids_path is None:
            return
        self._ids_path.parent.mkdir(parents=True, exist_ok=True)
        self._ids_path.write_text(json.dumps(self._ids, indent=2) + "\n", encoding="utf-8")


def _ids_path(graph: Graph) -> Path:
    return graph.root / ".agents" / "ids.json"


def _load_ids(graph: Graph) -> dict | None:
    """The registry must already exist (the workflow's id allocator creates it)."""
    if graph.ids is not None:
        return dict(graph.ids)
    p = _ids_path(graph)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def freeze(graph: Graph, ident: str, by: str = "", note: str = "") -> FreezePlan:
    resolved = resolve_content(graph, ident)
    if resolved is None:
        return FreezePlan("freeze", ident,
                          error=f"no story slug or seed id '{ident}' found to freeze")
    ids = _load_ids(graph)
    if ids is None:
        return FreezePlan("freeze", ident,
                          error="no .agents/ids.json registry (run the id allocator first)")
    kind, content = resolved
    entry = {"kind": kind, "hash": fingerprint(content),
             "approvedAt": datetime.now(timezone.utc).isoformat()}
    if by:
        entry["approvedBy"] = by
    if note:
        entry["note"] = note
    ids.setdefault("frozen", {})[ident] = entry
    return FreezePlan("freeze", ident, entry=entry, _ids_path=_ids_path(graph), _ids=ids)


def unfreeze(graph: Graph, ident: str) -> FreezePlan:
    ids = _load_ids(graph)
    if ids is None or ident not in (ids.get("frozen") or {}):
        return FreezePlan("unfreeze", ident, error=f"'{ident}' is not frozen")
    del ids["frozen"][ident]
    return FreezePlan("unfreeze", ident, _ids_path=_ids_path(graph), _ids=ids)
