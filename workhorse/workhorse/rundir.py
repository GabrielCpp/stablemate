"""Run identity and run-directory selection."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from workhorse.artifacts import ArtifactWriter
from workhorse.records import RunRecord, parse_run_record


def derive_run_id(run_id: str | None, params: dict[str, Any] | None) -> str | None:
    """Resolve the effective run id when ``--run-id`` was not given explicitly."""
    if run_id is not None:
        return run_id
    if not params:
        return None
    canon = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return "p" + hashlib.sha1(canon.encode()).hexdigest()[:8]


def resume_argv(
    program: str,
    run_dir: Path,
    *,
    cli: str = "",
    profile: str = "",
    config_path: str = "",
) -> list[str]:
    """The argv that resumes ``run_dir`` — rebuilt, never the original one replayed."""
    argv = [program, "run", "--resume-run", str(run_dir)]
    if cli and not profile:
        argv += ["--cli", cli]
    if profile:
        argv += ["--profile", profile]
    if config_path:
        argv += ["--config", config_path]
    return argv


def auto_resolve(
    runs_dir: Path, workflow_name: str, run_id: str | None = None
) -> tuple[str, Path | None]:
    """Resolve --auto's single stable run dir for this run id."""
    rid = run_id or "default"
    stable = runs_dir / f"{workflow_name}-{rid}"
    if not (stable / ArtifactWriter.CHECKPOINT_FILE).exists():
        return rid, None
    try:
        record = parse_run_record((stable / "run.json").read_text())
    except (OSError, ValidationError):
        record = RunRecord()
    if record.terminal is not None:
        return rid, None
    return rid, stable


def resolve_run_dir(spec: str, runs_dir: Path, workflow_name: str) -> Path | None:
    """The run dir an operator meant by ``spec``, or None if there is no such dir."""
    candidate = Path(spec)
    if not candidate.is_absolute() and not candidate.exists():
        candidate = runs_dir / spec
        if not candidate.is_dir():
            candidate = runs_dir / f"{workflow_name}-{spec}"
    resolved = candidate.resolve()
    return resolved if resolved.is_dir() else None


def find_latest_resumable(runs_dir: Path) -> Path | None:
    """Newest run dir that crashed mid-flight (has a checkpoint, never finished)."""
    if not runs_dir.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for d in runs_dir.iterdir():
        if not d.is_dir() or not (d / ArtifactWriter.CHECKPOINT_FILE).exists():
            continue
        try:
            record = parse_run_record((d / "run.json").read_text())
        except (OSError, ValidationError):
            continue
        if record.terminal is None:
            candidates.append(((d / ArtifactWriter.CHECKPOINT_FILE).stat().st_mtime, d))
    if not candidates:
        return None
    return max(candidates)[1]


def runtime_deadline(started_at_iso: str, budget_s: float) -> float | None:
    """Absolute unix-epoch deadline for this run, or None when no budget is set."""
    if budget_s <= 0:
        return None
    try:
        started = datetime.fromisoformat(started_at_iso)
    except ValueError:
        started = datetime.now(timezone.utc)
    return started.timestamp() + budget_s
