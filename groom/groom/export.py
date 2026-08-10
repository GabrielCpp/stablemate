"""Materializing the turn archive in the flat by-node layout distillation work reads.

The archive is run-major, because that is the shape a debugger arrives in: one run, one
node, its laps in order. A dataset wants the transpose — every session that ever ran a
given node, together, so a prompt can be evaluated against all of them. This module
writes that view:

```
<workflow>/<node>/<source>__<session_id>.json
INDEX.json
```

Two things separate it from the hand-rolled harvesters it replaces. Classification is
**exact**: the node a session belongs to is read from the index join that
``sessions.jsonl`` made possible, not guessed from a heading in the rendered prompt — so
there is no unclassified bucket. And the export is a *view*, materialized on demand into
a directory the caller names, so the canonical archive never holds a second copy of any
byte.

Everything streams. A single session's transcript runs to tens of megabytes and the
corpus does not fit in memory, so one session is read line by line into one output file
and neither is ever held whole. ``n_messages`` is therefore written *after* ``messages``
— a JSON object has no order, and counting first would mean reading twice.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from groom import store, turns

logger = logging.getLogger(__name__)

#: Anything outside this becomes ``_`` in a path component. Node and workflow names are
#: engine data, not attacker data, but they are free-form enough to contain a slash.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

#: Stand-in for a record whose capture layer did not say what it was. Named rather than
#: dropped: a turn with an unlabelled transcript is still a turn worth training on.
UNKNOWN_SOURCE = "unknown"


def _safe(value: str, fallback: str) -> str:
    cleaned = _UNSAFE.sub("_", value).strip("._-")
    return cleaned or fallback


def _iso(ts: Any) -> str:
    try:
        return dt.datetime.fromtimestamp(float(ts)).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _message_of(entry: dict[str, Any]) -> dict[str, Any] | None:
    """The message a transcript line carries, in the one shape every backend maps onto.

    A session store holds far more than messages — attachments, queue operations, summary
    records — and a line that is not a turn of the conversation is not a message. Rather
    than enumerate every backend's non-message kinds, this keeps what has a role and
    drops what does not.
    """
    message = entry.get("message")
    if isinstance(message, dict) and message.get("role"):
        kept = {"role": message.get("role"), "content": message.get("content")}
        if message.get("model"):
            kept["model"] = message["model"]
        return kept
    if entry.get("role"):
        return {"role": entry.get("role"), "content": entry.get("content")}
    return None


def _transcript_lines(record: Path) -> Iterator[dict[str, Any]]:
    """Parsed JSONL of one archived record, skipping what will not parse.

    A truncated capture ends mid-line by construction — the runner's byte cap cuts the
    file rather than dropping it — so the last line of a large transcript is routinely
    half a line. That is a reason to skip it, not to fail the export.
    """
    path = record / "transcript.jsonl"
    if not path.is_file():
        return
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                yield entry


def _write_session(row: dict[str, Any], target: Path) -> dict[str, Any]:
    """Write one session's JSON object, streaming its messages; the INDEX entry for it.

    ``cwd`` and ``model`` are whatever the transcript itself said, taken from the first
    line that offers each. They are properties of the session as it ran, and the index
    does not record them.
    """
    record = turns.record_path(row)
    session_id = str(row.get("session_id", ""))
    source = str(row.get("source", "")) or UNKNOWN_SOURCE
    cwd = ""
    model = ""
    count = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    # Written to a ``.part`` and moved into place: a session file is streamed, so an
    # interrupted export would otherwise leave a truncated object under a name that says
    # the session is there — and a dataset loader reads names, not sizes.
    partial = target.with_suffix(".json.part")
    with partial.open("w", encoding="utf-8") as out:
        head = {
            "task": str(row.get("node", "")),
            "source": source,
            "session_id": session_id,
            "run_id": str(row.get("run_id", "")),
            "workflow": str(row.get("workflow", "")),
            "generation": row.get("generation"),
            "seq": row.get("seq"),
            "time_created": _iso(row.get("ts")),
            "head": row.get("head"),
        }
        out.write(json.dumps(head)[:-1])  # open the object, keep writing into it
        out.write(', "messages": [')
        for entry in _transcript_lines(record):
            if not cwd and isinstance(entry.get("cwd"), str):
                cwd = entry["cwd"]
            message = _message_of(entry)
            if message is None:
                continue
            if not model and isinstance(message.get("model"), str):
                model = message["model"]
            out.write(("" if count == 0 else ", ") + json.dumps(message))
            count += 1
        out.write("]")
        out.write(f", {json.dumps({'n_messages': count, 'cwd': cwd, 'model': model})[1:]}")
    partial.replace(target)
    prompt = record / "prompt.md"
    return {
        **head,
        "n_messages": count,
        "cwd": cwd,
        "model": model,
        "bytes": target.stat().st_size,
        "has_prompt": prompt.is_file(),
    }


def export_by_node(
    target_dir: Path,
    *,
    workflow: str = "",
    run: str = "",
    node: str = "",
    limit: int = 1_000_000,
) -> dict[str, Any]:
    """Materialize the archive under ``target_dir`` as ``<workflow>/<node>/<file>.json``.

    Records with no transcript are still exported: their message list is empty, and the
    INDEX says so. Dropping them would make the export disagree with ``transcript ls``
    about how many times a node ran, which is the number the thrashing question turns on.
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, Any]] = []
    for row in store.query_turns(run=run, node=node, workflow=workflow, limit=limit):
        session_id = str(row.get("session_id", ""))
        if not session_id:
            continue
        source = _safe(str(row.get("source", "")) or UNKNOWN_SOURCE, UNKNOWN_SOURCE)
        relative = Path(
            _safe(str(row.get("workflow", "")), "unknown-workflow"),
            _safe(str(row.get("node", "")), "unknown-node"),
            f"{source}__{_safe(session_id, 'unknown-session')}.json",
        )
        try:
            entry = _write_session(row, target_dir / relative)
        except OSError:
            logger.debug("session not exported: %s", session_id, exc_info=True)
            continue
        index.append({**entry, "path": relative.as_posix()})
    (target_dir / "INDEX.json").write_text(
        json.dumps({"sessions": len(index), "records": index}, indent=2), encoding="utf-8"
    )
    return {"sessions": len(index), "dir": str(target_dir)}
