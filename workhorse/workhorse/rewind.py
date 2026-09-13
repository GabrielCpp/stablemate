"""Move a stopped run's checkpoint to another state — validated, backed up, and recorded.

The checkpoint is hand-editable by design (the driver validates it on the way back off
disk), and an operator repairing a run will edit it. What a text editor cannot do is
check the edit *before* the resume does: a mistyped state name or a param the target
state does not take is only found when the relaunched process dies on it, which is a
process image and a resume generation spent on a typo. This module is that edit, made
against the same rules the resume applies — the state resolves through
`Workflow.resolve_state`, the params bind through `coerce_params` against the state's
own signature — so a rewind that succeeds is one the resume will accept.

It spends nothing: no agent turn, no transition, no gas. The previous checkpoint is
copied beside the new one, and `events.jsonl` gets a `rewind` line, because a run whose
history silently jumps from one state to another reads, afterwards, like a driver bug.

It never touches a live run. A process holding the run dir rewrites the checkpoint at
its next transition, so a rewind under it is lost at best and interleaved at worst —
the caller refuses before calling this.
"""
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

#: The phase a rewind is recorded under in `events.jsonl`. Not a node visit: nothing
#: pairs it with a `done`, and a span reader ignores a phase it does not open.
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
    """Rewrite `run_dir`'s checkpoint to enter `to_state` with validated params.

    The params are the old checkpoint's, narrowed to `keep` when given and otherwise to
    the names `to_state` accepts, then overlaid with `set_params`. Carrying by name is
    the useful default: a rewind to an earlier state usually wants the same `budget` or
    `item` the later one held, and a name the target does not take is dropped and
    reported rather than failing the edit.
    """
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

    # Built the way a resume builds it, so an input the class retired is dropped here
    # exactly as it would be there rather than failing a rewind the resume would take.
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
            # As given, not coerced: the checkpoint holds JSON, and the resume coerces.
            "params": json.loads(json.dumps(params)),
            # A rewind leaves the gate it was parked on — re-arming that wait on resume
            # would park the rewound state on a question it never asked.
            "waiting_on": None,
            "updated_at": stamp.isoformat(),
        }
    )
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(rewritten.model_dump_json(indent=2))
    tmp.replace(path)

    # Validated from a dict: the rewind's own fields ride as extras, which the model
    # admits but a keyword call does not declare.
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
