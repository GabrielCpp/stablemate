"""Run identity and run-directory selection, shared by both engines.

The rules here — one stable dir per ``(workflow, run-id)``, an id derived from the
params when none is given, a finished run never resumed in place — are the resume
contract, not the YAML engine's implementation detail. The Python driver has to obey
exactly the same ones or ``--resume-latest`` would mean two different things depending
on which engine wrote the run, so they live in their own module rather than in
:mod:`workhorse.main`, which the driver cannot import (main imports *it*).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workhorse.artifacts import ArtifactWriter


def derive_run_id(run_id: str | None, params: dict[str, Any] | None) -> str | None:
    """Resolve the effective run id when ``--run-id`` was not given explicitly.

    An explicit ``--run-id`` always wins. Otherwise, when the run carries
    ``--params``, the id is a short deterministic digest of those params, so:

    - distinct param sets (``service=report`` vs ``service=api``) get distinct run
      dirs and never collide on a single ``default`` — the footgun where a second
      target silently resumes the first and its ``--params`` are ignored;
    - the SAME params re-resolve to the SAME id, so auto-resume-in-place is intact:
      a crash, reboot, or plain re-run of the same command still lands on the
      existing checkpoint (this is why it is a digest, not a random UUID — a UUID
      would orphan every unfinished run on the next launch).

    With no params it stays ``None`` → the caller's ``"default"`` (so a params-less
    workflow keeps its one stable dir, and the Docker harness — which pins no
    ``--run-id`` — still resumes across reboots exactly as before).
    """
    if run_id is not None:
        return run_id
    if not params:
        return None
    canon = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return "p" + hashlib.sha1(canon.encode()).hexdigest()[:8]


def auto_resolve(
    runs_dir: Path, workflow_name: str, run_id: str | None = None
) -> tuple[str, Path | None]:
    """Resolve --auto's single stable run dir for this run id.

    The run id here is already resolved by :func:`derive_run_id` (explicit
    ``--run-id``, else a params digest, else None); a None id falls back to "default",
    giving one fixed dir (e.g. ``research-default``). Returns ``(run_id, resume_dir)``
    where ``resume_dir`` is that dir when it already holds a checkpoint to continue,
    else None (caller starts fresh).

    A run that already reached a terminal node is NOT resumed — re-running means a
    new run, not a no-op replay of the finished one (mirrors
    :func:`find_latest_resumable`, which skips terminal runs). The fresh start reuses
    the same stable dir."""
    rid = run_id or "default"
    stable = runs_dir / f"{workflow_name}-{rid}"
    if not (stable / ArtifactWriter.CHECKPOINT_FILE).exists():
        return rid, None
    try:
        meta = json.loads((stable / "run.json").read_text())
    except (OSError, json.JSONDecodeError):
        meta = {}
    if meta.get("terminal") is not None:  # already finished — start a new run
        return rid, None
    return rid, stable


def find_latest_resumable(runs_dir: Path) -> Path | None:
    """Newest run dir that crashed mid-flight (has a checkpoint, never finished)."""
    if not runs_dir.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for d in runs_dir.iterdir():
        if not d.is_dir() or not (d / ArtifactWriter.CHECKPOINT_FILE).exists():
            continue
        try:
            meta = json.loads((d / "run.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if meta.get("terminal") is None:  # never reached a terminal node
            candidates.append(((d / ArtifactWriter.CHECKPOINT_FILE).stat().st_mtime, d))
    if not candidates:
        return None
    return max(candidates)[1]


def runtime_deadline(started_at_iso: str, budget_s: float) -> float | None:
    """Absolute unix-epoch deadline for this run, or None when no budget is set.

    Anchored to the writer's original ISO start time so a resumed run keeps the
    same deadline instead of restarting the clock. ``budget_s`` is the configured
    wall-clock ceiling (RunConfig.max_runtime_s); <= 0 means unbounded."""
    if budget_s <= 0:
        return None
    try:
        started = datetime.fromisoformat(started_at_iso)
    except ValueError:
        started = datetime.now(timezone.utc)
    return started.timestamp() + budget_s
