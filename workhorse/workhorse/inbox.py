"""A run-scoped inbox — the operator's half of the operator/worker channel."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    """One inbox entry."""

    model_config = ConfigDict(extra="allow")

    id: str
    body: str
    at: str
    reply: str = ""
    replied_at: str = ""


def _read_all(path: Path) -> list[Message]:
    p = Path(path)
    if not p.exists():
        return []
    messages = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            messages.append(Message.model_validate_json(line))
    return messages


def _write_all(path: Path, messages: list[Message]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(m.model_dump_json() + "\n" for m in messages)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, p)


def append(path: Path, *, id: str, body: str, at: str, **extra: Any) -> Message:
    """Append one message and return it."""
    message = Message.model_validate({"id": id, "body": body, "at": at, **extra})
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(message.model_dump_json() + "\n")
    return message


def all_messages(path: Path) -> list[Message]:
    """Every message ever appended, oldest first, replied or not."""
    return _read_all(path)


def outstanding(path: Path) -> list[Message]:
    """Messages with no reply yet, oldest first — what a poll point acts on."""
    return [m for m in _read_all(path) if not m.reply]


def reply(path: Path, message_id: str, text: str, *, at: str) -> Message:
    """Attach a reply to the message named ``message_id`` and return it updated."""
    messages = _read_all(path)
    hit = None
    for m in messages:
        if m.id == message_id:
            m.reply = text
            m.replied_at = at
            hit = m
    if hit is None:
        raise KeyError(f"no inbox message with id {message_id!r} in {path}")
    _write_all(path, messages)
    return hit
