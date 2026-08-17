"""The run-scoped operator inbox, polled from a workflow's own loop heads.

Workhorse's :mod:`workhorse.inbox` is the storage primitive; this is the one place both
`author` and `coder` reach for it, so the poll-and-consume behavior — reply to the oldest
outstanding message, which is what removes it from the next poll — is written once rather
than once per workflow. `Blueprint` registration is per-package, so this stays a plain
function; each workflow wraps it in its own thin `@blueprint.node`.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from workhorse import inbox as run_inbox
from workhorse.cli.inbox import INBOX_FILE


def poll_run_inbox(run_dir: str, *, reply_text: str) -> tuple[str, str] | None:
    """The oldest outstanding message in *run_dir*'s inbox, or `None` if there is none.

    Replying is what consumes it — a message replied to no longer shows up in the next
    poll's `outstanding()` — so one dropped note buys exactly one rework pass rather than
    looping the run forever. Returns `(body, scope)`; `scope` reads an operator-supplied
    `scope` field on the message when present (`"epic"` or `"story"`), and falls back to
    `"story"` — the inbox message format carries no such field today, so this is currently
    always `"story"` in practice.
    """
    if not run_dir:
        return None
    path = Path(run_dir) / INBOX_FILE
    pending = run_inbox.outstanding(path)
    if not pending:
        return None
    message = pending[0]
    run_inbox.reply(path, message.id, reply_text, at=datetime.now(UTC).isoformat())
    scope = getattr(message, "scope", "story")
    return message.body, (scope if scope in ("story", "epic") else "story")


__all__ = ["poll_run_inbox"]
