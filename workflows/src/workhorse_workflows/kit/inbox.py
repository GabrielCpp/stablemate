"""The run-scoped operator inbox, polled from a workflow's own loop heads."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from workhorse import inbox as run_inbox
from workhorse.cli.inbox import INBOX_FILE


def poll_run_inbox(run_dir: str, *, reply_text: str) -> tuple[str, str] | None:
    """The oldest outstanding message in *run_dir*'s inbox, or `None` if there is none."""
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
