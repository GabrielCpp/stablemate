"""The Dispatch pane follows the dispatch revision instead of polling, measured on the page the operator gets."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

from test_a11y_dynamic import (
    _DISPATCH_CONFIG,
    _UNAVAILABLE,
    _live,
    _open,
    teardown_module,  # noqa: F401
)


def _enqueue(live, queue: str, plan: str) -> dict:
    request = urllib.request.Request(
        live.url() + f"/api/dispatch/{queue}/items",
        data=json.dumps({"params": {"plan": plan}}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as reply:
        return json.loads(reply.read())


def test_the_dispatch_pane_makes_no_poll_and_shows_a_new_run_on_the_revision_push():
    from playwright.sync_api import expect

    from groom import dispatch_ledger

    live = _live()
    assert live is not None, _UNAVAILABLE
    config = Path(live.tmp.name) / "dispatch-follow.toml"
    config.write_text(_DISPATCH_CONFIG)
    with patch.dict(os.environ, {"STABLEMATE_CONFIG": str(config)}):
        page = _open(live)
        item_id = ""
        try:
            page.click('.act-btn[data-mode="dispatch"]')
            page.get_by_role("button", name=re.compile("plans")).click()
            page.wait_for_load_state("networkidle")
            seen: list[str] = []
            page.on("request", lambda request: seen.append(request.url) if "/api/dispatch" in request.url else None)
            time.sleep(6)
            assert seen == [], f"the pane polled: {seen}"

            item_id = _enqueue(live, "plans", "follow-me.md")["item"]["item_id"]
            row = page.get_by_role("button", name=re.compile(re.escape(item_id)))
            expect(row).to_be_visible(timeout=30000)
            assert seen, "the row showed with no read of the dispatch pane after the revision moved"
        finally:
            page.close()
            if item_id:
                dispatch_ledger.dispatch_cancel_pending(item_id)
