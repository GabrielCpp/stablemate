"""A run-scoped inbox — the operator's half of the operator/worker channel.

The counterpart to :mod:`workhorse.gates`: a gate is the **worker's** question,
one at a time, blocking; an inbox message is the **operator's** note, any number
outstanding, advisory only — nothing appended here can halt or steer a run by
itself. A workflow's poll point decides what (if anything) an outstanding message
changes; this module only stores and retrieves them.

Same shape as :mod:`workhorse.worklist`: a pydantic model with ``extra="allow"``
so a workflow's own fields (``kind``, ``target``, whatever a particular poll point
wants to key on) ride alongside the ones this primitive knows, and every function
**returns a value and never prints or exits**. Storage is JSON-lines at
``<run_dir>/inbox.jsonl`` — append-only until a reply rewrites one line — because
an inbox is written by an operator (by hand, or through groom) and read by a
workflow poll point that only ever wants "what's new", not a query language.

This is also the failure-handoff channel: when a node raises
:class:`~workhorse.pyflow.errors.WorkflowFailed`, the driver appends a message
here rather than only printing to a log a resumed process no longer holds — see
``workhorse/pyflow/run.py``'s terminal-failure handling. ``kind="failure"``
distinguishes that diagnostic entry from an operator's own note; nothing in this
module treats one kind specially, so a workflow poll point (or a babysitting
agent) filters for it the same way it would filter for any other ``kind``.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    """One inbox entry.

    ``id`` is caller-supplied (a ULID or short handle from whatever minted it) so
    a re-append of the same logical message is idempotent to *reply* — replying
    finds the entry by ``id`` regardless of how many other messages have landed
    since. ``reply``/``replied_at`` are set together, and their being empty is
    what makes a message outstanding: there is no separate status field to drift
    out of sync with them.
    """

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
    """Append one message and return it. A plain append — no read-modify-write of
    the existing file — so two writers appending at once cannot clobber each
    other's line, only interleave, which JSON-lines already tolerates."""
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
    """Attach a reply to the message named ``message_id`` and return it updated.

    This is the one operation that rewrites rather than appends, so it is not
    safe against a concurrent ``reply`` to the *same* message racing this one —
    the whole file is read, the one line changed, and the whole file rewritten
    atomically. Concurrent replies to different messages are fine; nothing in
    this design has two writers replying to the same message at once.
    """
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
