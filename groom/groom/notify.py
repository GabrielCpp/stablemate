"""Outbound AFK notifications — the piece that reaches a phone.

Browser Notification needs an open tab; these don't. Two stdlib-``urllib``
channels, both opt-in via env and both best-effort (short timeout, silent on
failure — an unreachable notifier must never wedge the collector), modeled on
the sidecar's fire-and-forget ``_push``:

- **ntfy**: ``GROOM_NTFY_TOPIC=<topic>`` posts to ``GROOM_NTFY_URL``
  (default ``https://ntfy.sh``)/<topic> — install the ntfy app, subscribe to
  the topic, done.
- **generic webhook**: ``GROOM_WEBHOOK_URL=<url>`` receives a JSON body
  ``{"title", "message"}`` (Slack-style receivers, home automation, …).

Callers run :func:`push` off the event loop (``asyncio.to_thread``) since
urllib blocks.
"""

from __future__ import annotations

import json
import os
import urllib.request

PUSH_TIMEOUT_S = float(os.environ.get("GROOM_NOTIFY_TIMEOUT", "5.0"))


def _post(url: str, data: bytes, headers: dict[str, str]) -> None:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        urllib.request.urlopen(request, timeout=PUSH_TIMEOUT_S).close()  # noqa: S310
    except Exception:
        pass  # best-effort: alerting must never take the collector down with it


def push(title: str, message: str) -> None:
    """Send ``message`` to every configured channel (none configured = no-op).
    Env is read per call so long-lived groom picks up changes on restart only,
    but tests can patch os.environ without reimporting."""
    topic = os.environ.get("GROOM_NTFY_TOPIC", "").strip()
    if topic:
        base = os.environ.get("GROOM_NTFY_URL", "https://ntfy.sh").rstrip("/")
        _post(
            f"{base}/{topic}",
            message.encode("utf-8"),
            {"Title": title.encode("latin-1", "replace").decode("latin-1")},
        )
    webhook = os.environ.get("GROOM_WEBHOOK_URL", "").strip()
    if webhook:
        _post(
            webhook,
            json.dumps({"title": title, "message": message}).encode("utf-8"),
            {"Content-Type": "application/json"},
        )
