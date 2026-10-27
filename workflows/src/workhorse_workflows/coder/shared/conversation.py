"""The story's backbone conversation: the one session its primary turns share."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from workhorse.pyflow import Workflow


def story_chain(slug: str) -> str:
    """The chain name a story's primary turns share across lanes."""
    return f"story:{slug}"


def brief_dir(state_dir: Path, work_id: str) -> Path:
    """Where the briefs of work item `work_id` and their ledger live."""
    return state_dir / "briefs" / work_id.replace("/", "__")


def brief_ledger(state_dir: Path, work_id: str) -> dict[str, str]:
    """Each phase, by the conversation id its last turn ran on."""
    try:
        loaded = json.loads((brief_dir(state_dir, work_id) / "ledger.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(k): str(v) for k, v in loaded.items()}


def record_brief(state_dir: Path, work_id: str, phase: str, session: str) -> None:
    """Note that `phase`'s last turn ran on conversation `session`."""
    ledger = brief_ledger(state_dir, work_id) | {phase: session}
    path = brief_dir(state_dir, work_id) / "ledger.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def reset_briefs(state_dir: Path, work_id: str) -> None:
    """Forget every phase this work item briefed, so each phase opens with its brief again."""
    shutil.rmtree(brief_dir(state_dir, work_id), ignore_errors=True)


def needs_brief(ledger: dict[str, str], phase: str, session: str) -> bool:
    """Whether `phase` opens with its full brief: no conversation yet, or not the one it was briefed on."""
    return not session or ledger.get(phase) != session


def opening_phase(ledger: dict[str, str], session: str) -> str:
    """The first phase briefed on conversation `session`, whose brief carries the story's rules, or empty when none was."""
    if not session:
        return ""
    return next((phase for phase, on in ledger.items() if on == session), "")


def backbone(flow: Workflow) -> str:
    """The chain the story on this flow's `ctx` runs its primary turns on."""
    return story_chain(flow.ctx.story_slug)


__all__ = [
    "backbone",
    "brief_dir",
    "brief_ledger",
    "needs_brief",
    "opening_phase",
    "record_brief",
    "reset_briefs",
    "story_chain",
]
