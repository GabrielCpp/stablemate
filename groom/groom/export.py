"""Materializing the turn archive in the flat by-node layout distillation work reads."""

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

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

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
    """The message a transcript line carries, in the one shape every backend maps onto."""
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
    """Parsed records from one archived JSONL stream or full-session JSON export."""
    path = record / "transcript.jsonl"
    if path.is_file():
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
        return

    try:
        payload = json.loads((record / "transcript.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    messages = payload.get("messages", []) if isinstance(payload, dict) else []
    for item in messages if isinstance(messages, list) else []:
        if not isinstance(item, dict):
            continue
        info, parts = item.get("info", {}), item.get("parts", [])
        if not isinstance(info, dict) or not isinstance(parts, list):
            continue
        model, provider = info.get("modelID"), info.get("providerID")
        full_model = (
            f"{provider}/{model}"
            if isinstance(provider, str) and provider and isinstance(model, str) and model
            else model
        )
        message: dict[str, Any] = {"role": info.get("role"), "content": parts}
        if isinstance(full_model, str) and full_model:
            message["model"] = full_model
        entry: dict[str, Any] = {"message": message}
        path_info = info.get("path", {})
        if isinstance(path_info, dict) and isinstance(path_info.get("cwd"), str):
            entry["cwd"] = path_info["cwd"]
        yield entry


def _write_session(row: dict[str, Any], target: Path) -> dict[str, Any]:
    """Write one session's JSON object, streaming its messages; the INDEX entry for it."""
    record = turns.record_path(row)
    session_id = str(row.get("session_id", ""))
    source = str(row.get("source", "")) or UNKNOWN_SOURCE
    cwd = ""
    model = ""
    count = 0
    target.parent.mkdir(parents=True, exist_ok=True)
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
        out.write(json.dumps(head)[:-1])
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
    """Materialize the archive under ``target_dir`` as ``<workflow>/<node>/<file>.json``."""
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
