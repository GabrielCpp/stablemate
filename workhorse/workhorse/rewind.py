"""Move a stopped run's checkpoint to another state — validated, backed up, and recorded."""
from __future__ import annotations

import inspect
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow.driver import coerce_params
from workhorse.pyflow.errors import UnknownStateError, WorkflowDefinitionError, WorkflowFailed
from workhorse.pyflow.registry import Registry
from workhorse.records import NodeEvent, PyflowCheckpoint, parse_checkpoint

REWIND_PHASE: Final = "rewind"


class RewindError(Exception):
    """The rewind was refused; the checkpoint on disk is unchanged."""


@dataclass(frozen=True)
class Rewound:
    """What a rewind did, for the operator's report."""

    from_state: str
    to_state: str
    params: dict[str, Any]
    dropped: tuple[str, ...]
    backup: Path


def rewind(
    run_dir: Path,
    registry: Registry,
    to_state: str,
    *,
    set_params: dict[str, Any] | None = None,
    keep: list[str] | None = None,
    now: datetime | None = None,
) -> Rewound:
    """Rewrite `run_dir`'s checkpoint to enter `to_state` with validated params."""
    path = run_dir / ArtifactWriter.CHECKPOINT_FILE
    try:
        checkpoint = parse_checkpoint(path.read_text())
    except (OSError, ValidationError) as exc:
        raise RewindError(f"cannot read checkpoint {path}: {exc}") from exc
    if not isinstance(checkpoint, PyflowCheckpoint):
        raise RewindError(f"{path} is a checkpoint from the retired YAML engine")

    workflow_cls = registry.class_named(checkpoint.flow)
    if workflow_cls is None:
        if checkpoint.flow:
            raise RewindError(
                f"{path} names flow {checkpoint.flow!r}, which {registry.name!r} does not "
                "register — rewind it with the command of the workflow that wrote it"
            )
        try:
            workflow_cls = registry.flow(None)
        except WorkflowDefinitionError as exc:
            raise RewindError(str(exc)) from exc
    try:
        spec = workflow_cls.resolve_state(to_state)
    except UnknownStateError as exc:
        raise RewindError(str(exc)) from exc

    inputs = {k: v for k, v in checkpoint.inputs.items() if k in workflow_cls.model_fields}
    try:
        wf = workflow_cls(**inputs)
    except ValidationError as exc:
        raise RewindError(
            f"{workflow_cls.__name__} cannot be built from the checkpoint's inputs:\n{exc}"
        ) from exc
    bound = getattr(wf, spec.name)

    accepted = set(inspect.signature(bound).parameters)
    carried = set(keep) if keep is not None else accepted
    unknown_keep = sorted(carried - set(checkpoint.params)) if keep is not None else []
    if unknown_keep:
        raise RewindError(
            f"--keep names {', '.join(unknown_keep)}, which the checkpoint does not hold. "
            f"It holds: {', '.join(sorted(checkpoint.params)) or '(none)'}"
        )
    params = {k: v for k, v in checkpoint.params.items() if k in carried and k in accepted}
    params.update(set_params or {})
    dropped = tuple(sorted(set(checkpoint.params) - set(params)))
    try:
        coerce_params(bound, params, state=spec.name)
    except WorkflowFailed as exc:
        raise RewindError(str(exc)) from exc

    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    backup = path.with_name(f"checkpoint.rewound-{stamp.strftime('%Y%m%dT%H%M%SZ')}.json")
    shutil.copyfile(path, backup)
    rewritten = checkpoint.model_copy(
        update={
            "state": spec.name,
            "params": json.loads(json.dumps(params)),
            "waiting_on": None,
            "updated_at": stamp.isoformat(),
        }
    )
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(rewritten.model_dump_json(indent=2))
    tmp.replace(path)

    event = NodeEvent.model_validate({
        "ts": stamp.isoformat(),
        "seq": checkpoint.seq,
        "node": spec.name,
        "phase": REWIND_PHASE,
        "from_state": checkpoint.state,
        "from_waiting_on": checkpoint.waiting_on,
        "dropped": list(dropped),
        "backup": backup.name,
    })
    with (run_dir / ArtifactWriter.EVENTS_FILE).open("a") as events:
        events.write(event.model_dump_json() + "\n")

    return Rewound(checkpoint.state, spec.name, rewritten.params, dropped, backup)


__all__ = ["REWIND_PHASE", "RewindError", "Rewound", "rewind"]
