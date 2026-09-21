"""Outbound AFK notifications — the piece that reaches a phone."""

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
        pass


def push(title: str, message: str) -> None:
    """Send ``message`` to every configured channel (none configured = no-op)."""
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
