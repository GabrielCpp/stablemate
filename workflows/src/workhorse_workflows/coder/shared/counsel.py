"""The advisor consults a work item's review recorded, kept across its turns."""
from __future__ import annotations

import json
from pathlib import Path

from workhorse_workflows.coder.shared.schemas.dev_story import Consult


def counsel_path(state_dir: Path, work_id: str) -> Path:
    """The file work item `work_id`'s consults are kept in."""
    return state_dir / "counsel" / f"{work_id.replace('/', '__')}.json"


def _read(state_dir: Path, work_id: str) -> dict[str, dict[str, str]]:
    try:
        loaded = json.loads(counsel_path(state_dir, work_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def record_consults(state_dir: Path, work_id: str, consults: list[Consult]) -> None:
    """Keep each consult by its finding id, a later one replacing an earlier one."""
    if not consults:
        return
    kept = _read(state_dir, work_id)
    for consult in consults:
        kept[consult.finding] = consult.model_dump()
    path = counsel_path(state_dir, work_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(kept, indent=2), encoding="utf-8")


def consulted(state_dir: Path, work_id: str) -> set[str]:
    """The finding ids with a consult on file."""
    return set(_read(state_dir, work_id))


__all__ = ["consulted", "counsel_path", "record_consults"]
