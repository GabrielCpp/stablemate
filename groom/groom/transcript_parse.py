"""One stored turn read into the attendant view's entry shape, whichever backend wrote it."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from groom.attend_transcript import _result_text, _text_of
from groom.projection import transcript_entry

Window = tuple[float, float]

MAX_RESULT_CHARS = 4000


def _records(path: Path) -> Iterator[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    yield record
    except OSError:
        return


def _epoch(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1000.0 if value > 1e11 else float(value)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _within(ts: float | None, window: Window | None) -> bool:
    return window is None or ts is None or window[0] <= ts <= window[1]


def _message(role: str, text: str) -> dict[str, Any]:
    return {"kind": "message", "role": role, "text": text, "collapsed": role == "user"}


SUMMARY_KEYS = ("file_path", "filePath", "path", "command", "pattern", "query", "url", "description", "prompt")


def _tool_summary(args: Any) -> str:
    if isinstance(args, dict):
        for key in SUMMARY_KEYS:
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().splitlines()[0][:160]
    return ""


def _tool(name: str, summary: str, detail: str = "", result: str = "", failed: bool = False) -> dict[str, Any]:
    return {
        "kind": "tool", "name": name, "summary": summary,
        "detail": detail[:MAX_RESULT_CHARS], "result": result[:MAX_RESULT_CHARS], "failed": failed,
    }


def _args_text(args: Any) -> str:
    if isinstance(args, str):
        return args
    return json.dumps(args, indent=2, default=str) if args else ""


CHUNKS = ("user_message_chunk", "agent_message_chunk", "agent_thought_chunk")


def from_updates(updates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """ACP updates, the live transcript's own shape, as entries; streamed chunks join and a call's updates merge."""
    merged: list[dict[str, Any]] = []
    slots: dict[str, int] = {}
    for update in updates:
        kind = str(update.get("sessionUpdate") or "")
        call_id = str(update.get("toolCallId") or "")
        if call_id in slots:
            into = merged[slots[call_id]]
            into.update({k: v for k, v in update.items() if k != "sessionUpdate" or kind == "tool_call"})
            continue
        content = update.get("content")
        if kind in CHUNKS and merged and merged[-1].get("sessionUpdate") == kind and isinstance(content, dict):
            previous = merged[-1]["content"]
            previous["text"] = str(previous.get("text") or "") + str(content.get("text") or "")
            continue
        merged.append({**update, "content": dict(content)} if kind in CHUNKS and isinstance(content, dict) else dict(update))
        if call_id:
            slots[call_id] = len(merged) - 1
    return [transcript_entry(update) for update in merged]


def _acp(path: Path) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for record in _records(path):
        if record.get("truncated"):
            updates.append({"sessionUpdate": "truncated", "bytes": record.get("bytes", 0)})
            continue
        update = record.get("update")
        if isinstance(update, dict):
            updates.append(update)
    return from_updates(updates)


def _claude(path: Path, window: Window | None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pending: dict[str, dict[str, Any]] = {}
    for record in _records(path):
        if not _within(_epoch(record.get("timestamp")), window):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or record.get("type") or "")
        content = message.get("content")
        blocks = [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []
        results = [block for block in blocks if block.get("type") == "tool_result"]
        for block in results:
            call = pending.pop(str(block.get("tool_use_id") or ""), None)
            if call is not None:
                call["result"] = _result_text(block.get("content"))
                call["failed"] = bool(block.get("is_error"))
        if results:
            continue
        text = _text_of(content)
        if text:
            entries.append(_message(role, text))
        for block in blocks:
            if block.get("type") == "thinking" and block.get("thinking"):
                entries.append(_message("thought", str(block["thinking"])))
            if block.get("type") != "tool_use":
                continue
            name = str(block.get("name") or "tool")
            args = block.get("input")
            call = _tool(name, _tool_summary(args), _args_text(args))
            entries.append(call)
            if block.get("id"):
                pending[str(block["id"])] = call
    return entries


def _command_line(command: Any) -> str:
    if isinstance(command, list):
        parts = [str(part) for part in command]
        if len(parts) == 3 and parts[1] in ("-c", "-lc"):
            return parts[2]
        return " ".join(parts)
    return str(command or "")


def _codex(path: Path, window: Window | None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in _records(path):
        payload = record.get("payload")
        if record.get("type") != "event_msg" or not isinstance(payload, dict):
            continue
        if payload.get("type") != "item_completed" or not isinstance(payload.get("item"), dict):
            continue
        if not _within(_epoch(record.get("timestamp")), window):
            continue
        item = payload["item"]
        kind = item.get("type")
        if kind in ("AgentMessage", "UserMessage"):
            text = _text_of([{"type": "text", "text": block.get("text")} for block in item.get("content") or [] if isinstance(block, dict)])
            if text:
                entries.append(_message("assistant" if kind == "AgentMessage" else "user", text))
        elif kind == "Reasoning":
            summary = item.get("summary_text")
            text = "\n".join(str(part) for part in summary) if isinstance(summary, list) else ""
            if text.strip():
                entries.append(_message("thought", text))
        elif kind == "CommandExecution":
            command = _command_line(item.get("command"))
            code = item.get("exit_code")
            failed = item.get("status") == "failed" or (isinstance(code, int) and code != 0)
            first = command.strip().splitlines()[0] if command.strip() else "command"
            entries.append(_tool("shell", first[:160], command, str(item.get("aggregated_output") or ""), failed))
        elif kind == "FileChange":
            changes = item.get("changes")
            paths = sorted(changes) if isinstance(changes, dict) else []
            entries.append(_tool("edit", ", ".join(paths)[:160], "\n".join(paths)))
    return entries


def _opencode_tool(part: dict[str, Any]) -> dict[str, Any]:
    name = str(part.get("tool") or "tool")
    raw = part.get("state")
    state: dict[str, Any] = raw if isinstance(raw, dict) else {}
    args = state.get("input")
    output = state.get("output")
    return _tool(
        name, _tool_summary(args), _args_text(args),
        output if isinstance(output, str) else "", state.get("status") == "error",
    )


def _opencode_tee(path: Path, window: Window | None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in _records(path):
        part = record.get("part")
        if not isinstance(part, dict) or not _within(_epoch(record.get("timestamp")), window):
            continue
        if record.get("type") == "text" and str(part.get("text") or "").strip():
            entries.append(_message("assistant", str(part["text"]).strip()))
        elif record.get("type") == "reasoning" and str(part.get("text") or "").strip():
            entries.append(_message("thought", str(part["text"]).strip()))
        elif record.get("type") == "tool_use":
            entries.append(_opencode_tool(part))
    return entries


def _opencode_export(path: Path, window: Window | None) -> list[dict[str, Any]]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return []
    messages = loaded.get("messages") if isinstance(loaded, dict) else None
    entries: list[dict[str, Any]] = []
    for message in messages if isinstance(messages, list) else []:
        if not isinstance(message, dict):
            continue
        raw_info = message.get("info")
        info: dict[str, Any] = raw_info if isinstance(raw_info, dict) else {}
        raw_time = info.get("time")
        created = raw_time.get("created") if isinstance(raw_time, dict) else None
        if not _within(_epoch(created), window):
            continue
        role = "user" if info.get("role") == "user" else "assistant"
        for part in message.get("parts") or []:
            if not isinstance(part, dict):
                continue
            text = str(part.get("text") or "").strip()
            if part.get("type") == "text" and text:
                entries.append(_message(role, text))
            elif part.get("type") == "reasoning" and text:
                entries.append(_message("thought", text))
            elif part.get("type") == "tool":
                entries.append(_opencode_tool(part))
    return entries


def _first_record(path: Path) -> dict[str, Any]:
    return next(_records(path), {})


def _jsonl(path: Path, window: Window | None) -> list[dict[str, Any]]:
    first = _first_record(path)
    if "payload" in first:
        return _codex(path, window)
    if "part" in first or first.get("type") in ("step_start", "text", "tool_use", "reasoning"):
        return _opencode_tee(path, window)
    return _claude(path, window)


def read_files(files: dict[str, Path], window: Window | None = None) -> list[dict[str, Any]] | None:
    """The entries of one record's files by name, or None when the record holds no transcript.

    A record written by a resumed session holds every turn of that session, so ``window`` keeps the entries stamped inside one turn.
    """
    acp = files.get("transcript.acp.jsonl")
    if acp is not None and acp.is_file():
        return _acp(acp)
    jsonl = files.get("transcript.jsonl")
    if jsonl is not None and jsonl.is_file():
        return _jsonl(jsonl, window)
    export = files.get("transcript.json")
    if export is not None and export.is_file():
        return _opencode_export(export, window)
    return None


def read_directory(directory: Path, window: Window | None = None) -> list[dict[str, Any]] | None:
    try:
        files = {path.name: path for path in directory.iterdir() if path.is_file()}
    except OSError:
        return None
    return read_files(files, window)
