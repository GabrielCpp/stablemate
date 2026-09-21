"""The attendant's own transcript root, and the reader that turns one into prose."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from workhorse.runner import transcript as capture

from groom import turns

logger = logging.getLogger(__name__)

ATTEND_DIR = "attend"

MAX_SESSION_BYTES = turns.MAX_RECORD_BYTES

MAX_DETAIL_CHARS = 4000


def attend_root() -> Path:
    """``<groom data dir>/transcripts/attend`` — the sibling of the run-major tree."""
    return turns.transcripts_root() / ATTEND_DIR


def session_dir(session_id: str) -> Path:
    return attend_root() / session_id


def copy_session(session_id: str) -> int:
    """Copy this session out of the CLI's store into groom's; bytes written."""
    if not session_id:
        return 0
    try:
        sources = capture._claude_store(session_id)  # noqa: SLF001 - the one resolver
    except Exception:
        logger.debug("attend: could not resolve the store for %s", session_id)
        return 0
    if not sources:
        return 0

    target = session_dir(session_id)
    written = 0
    try:
        target.mkdir(parents=True, exist_ok=True)
        for source in sources:
            if source.is_dir():
                dest = target / source.name
                shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(source, dest, dirs_exist_ok=True)
            else:
                shutil.copyfile(source, target / source.name)
        written = sum(p.stat().st_size for p in target.rglob("*") if p.is_file())
    except OSError as exc:
        logger.warning("attend: transcript copy for %s incomplete: %s", session_id, exc)
    return written


def has_body(session_id: str) -> bool:
    directory = session_dir(session_id)
    return bool(session_id) and directory.is_dir() and any(directory.rglob("*.jsonl"))


def ensure_body(session_id: str) -> bool:
    """Copy on first read when the exit-time copy did not happen (or groom was killed)."""
    if has_body(session_id):
        return True
    copy_session(session_id)
    return has_body(session_id)




def _text_of(content: Any) -> str:
    """Every text block in a message body, joined."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or "").strip())
    return "\n\n".join(part for part in parts if part).strip()


def _tool_summary(name: str, args: Any) -> str:
    """One line naming what the call was *about* — the path, the command, the pattern."""
    if not isinstance(args, dict):
        return name
    for key in ("file_path", "path", "command", "pattern", "query", "url", "prompt"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            first = value.strip().splitlines()[0]
            return f"{name}: {first[:160]}"
    return name


def _detail_of(args: Any) -> str:
    """The call's arguments as prose, one ``key: value`` per line — never raw JSON."""
    if isinstance(args, str):
        return args[:MAX_DETAIL_CHARS]
    if not isinstance(args, dict):
        return ""
    lines: list[str] = []
    for key, value in args.items():
        rendered = value if isinstance(value, str) else json.dumps(value, default=str)
        lines.append(f"{key}: {rendered}")
    return "\n".join(lines)[:MAX_DETAIL_CHARS]


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content[:MAX_DETAIL_CHARS]
    if isinstance(content, list):
        parts = [
            str(block.get("text") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(parts)[:MAX_DETAIL_CHARS]
    return ""


def _entries(path: Path, sidechain: bool = False) -> list[dict[str, Any]]:
    """One transcript file as an ordered list of rendered entries."""
    entries: list[dict[str, Any]] = []
    pending: dict[str, dict[str, Any]] = {}
    try:
        raw = path.read_text(errors="replace")
    except OSError:
        return entries

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or record.get("type") or "")
        content = message.get("content")

        results = [
            block
            for block in (content if isinstance(content, list) else [])
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]
        for block in results:
            call = pending.pop(str(block.get("tool_use_id") or ""), None)
            text = _result_text(block.get("content"))
            if call is not None:
                call["result"] = text
                call["failed"] = bool(block.get("is_error"))
            elif text:
                entries.append({"kind": "tool", "name": "result", "summary": "result",
                                "detail": "", "result": text, "failed":
                                bool(block.get("is_error")), "sidechain": sidechain})
        if results:
            continue

        text = _text_of(content)
        if text:
            entries.append({"kind": "message", "role": role, "text": text,
                            "sidechain": sidechain})

        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = str(block.get("name") or "tool")
            args = block.get("input")
            call = {
                "kind": "tool",
                "name": name,
                "summary": _tool_summary(name, args),
                "detail": _detail_of(args),
                "result": "",
                "failed": False,
                "sidechain": sidechain,
            }
            entries.append(call)
            use_id = str(block.get("id") or "")
            if use_id:
                pending[use_id] = call

    return entries


def render_session(session_id: str) -> dict[str, Any]:
    """The whole session as a conversation, subagent sidechains folded in after it."""
    directory = session_dir(session_id)
    main = directory / f"{session_id}.jsonl"
    entries: list[dict[str, Any]] = []
    if main.is_file():
        entries.extend(_entries(main))
    sidechains = directory / session_id
    if sidechains.is_dir():
        for path in sorted(sidechains.rglob("*.jsonl")):
            found = _entries(path, sidechain=True)
            if found:
                entries.append({"kind": "divider", "label": f"subagent · {path.stem}"})
                entries.extend(found)
    return {
        "session_id": session_id,
        "present": bool(entries),
        "path": str(directory),
        "entries": entries,
    }
