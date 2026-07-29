"""Tests for the dashboard's connection state machine (assets/dashboard.js).

The machine is the reason the dashboard can be trusted at a glance: a half-open
TCP socket reads ``readyState === OPEN`` forever and will never deliver another
frame, so the chip is derived from *message recency* instead. The server ticks
every ``GROOM_LIVE_TICK_S`` whether or not anything changed, which is what makes
silence mean something.

``deriveConnection`` is a pure function of (now, socketOpen, lastMessageTs,
closedSince) precisely so it can be asserted against synthetic timestamps rather
than a real socket, which is what this file does — through node, because the unit
under test is JavaScript. When node is absent the assertions are skipped and said
so out loud; the Playwright a11y suite exercises the same module in a browser.

Run: uv run pytest tests/test_connection_state.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "groom" / "assets"
NODE = shutil.which("node")

# Exercise the real module. Its only import is the vendored htm/preact build, and
# its module body mounts the islands into a DOM that does not exist under node —
# so pull just the pure function out of the source rather than importing it, and
# assert (below) that what was pulled is the definition the browser gets.
_HARNESS = """
import {{ readFileSync }} from "node:fs";
const src = readFileSync({path}, "utf8");
const start = src.indexOf("export function deriveConnection");
const end = src.indexOf("export function backoffDelay");
const body = src.slice(start, end).replace(/^export /gm, "");
const consts = src.match(/^export const (STALE_AFTER_MS|OFFLINE_AFTER_MS) = \\d+;$/gm)
  .join("\\n").replace(/^export /gm, "");
const deriveConnection = new Function(consts + "\\n" + body + "\\nreturn deriveConnection;")();
const out = JSON.parse(process.env.GROOM_OBS).map((obs) => deriveConnection(obs));
console.log(JSON.stringify(out));
"""


def _derive(observations: list[dict]) -> list[dict] | None:
    """Run the JS machine over a list of observations. None when node is absent."""
    if NODE is None:
        return None
    harness = _HARNESS.format(path=json.dumps(str(ASSETS / "dashboard.js")))
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", harness],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "GROOM_OBS": json.dumps(observations)},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _skipped() -> bool:
    if NODE is None:
        print("SKIP  node not on PATH — connection state machine not exercised", file=sys.stderr)
        return True
    return False


def test_source_defines_the_thresholds_the_harness_extracts():
    # The harness slices the function out of the source; if either the export or
    # the threshold constants are renamed, the slicing would quietly test nothing.
    src = (ASSETS / "dashboard.js").read_text()
    assert "export function deriveConnection" in src
    assert "export const STALE_AFTER_MS = 15000;" in src
    assert "export const OFFLINE_AFTER_MS = 60000;" in src


def test_the_open_pane_is_pushed_not_polled():
    # Phase 2 traded a per-tab `setInterval` fetch of /worker/{id}/live for a
    # subscription. The interval has to be gone, not merely unused: a leftover one
    # would keep hitting a route that no longer exists, on every open tab.
    src = (ASSETS / "dashboard.js").read_text()
    assert "LIVE_POLL_MS" not in src
    assert '+ "/live"' not in src
    assert 'cmd: "watch"' in src
    # Re-declared on reconnect (the server forgets a tab the moment it drops) and
    # on selection — but only *after* the pane it targets exists in the DOM.
    assert src.count("sendWatch(") >= 3


def test_open_socket_receiving_frames_is_live():
    if _skipped():
        return
    now = 1_000_000
    [live] = _derive([{"now": now, "socketOpen": True, "lastMessageTs": now - 4_000, "closedSince": 0}])
    assert live == {"phase": "live", "resyncing": False}


def test_open_but_silent_socket_goes_stale_and_starts_resyncing():
    # Three missed server ticks. The socket still claims to be open — this is the
    # case `readyState` cannot see, and the only reason the machine exists.
    if _skipped():
        return
    now = 1_000_000
    [stale] = _derive([{"now": now, "socketOpen": True, "lastMessageTs": now - 20_000, "closedSince": 0}])
    assert stale == {"phase": "stale", "resyncing": True}


def test_a_closed_socket_reconnects_then_goes_offline():
    if _skipped():
        return
    now = 1_000_000
    reconnecting, offline = _derive([
        {"now": now, "socketOpen": False, "lastMessageTs": now - 30_000, "closedSince": now - 10_000},
        {"now": now, "socketOpen": False, "lastMessageTs": now - 300_000, "closedSince": now - 120_000},
    ])
    assert reconnecting == {"phase": "reconnecting", "resyncing": True}
    assert offline == {"phase": "offline", "resyncing": True}


def test_the_full_live_to_stale_to_offline_progression():
    # One socket, observed as time passes: it is answering, then it stops, then it
    # drops. Everything past `live` must be resyncing over HTTP, or the tab shows a
    # frozen fleet with no indication that it is frozen.
    if _skipped():
        return
    t0 = 1_000_000
    phases = _derive([
        {"now": t0, "socketOpen": True, "lastMessageTs": t0, "closedSince": 0},
        {"now": t0 + 20_000, "socketOpen": True, "lastMessageTs": t0, "closedSince": 0},
        {"now": t0 + 25_000, "socketOpen": False, "lastMessageTs": t0, "closedSince": t0 + 21_000},
        {"now": t0 + 120_000, "socketOpen": False, "lastMessageTs": t0, "closedSince": t0 + 21_000},
    ])
    assert [p["phase"] for p in phases] == ["live", "stale", "reconnecting", "offline"]
    assert [p["resyncing"] for p in phases] == [False, True, True, True]


def test_backoff_grows_and_is_capped():
    if _skipped():
        return
    src = (ASSETS / "dashboard.js").read_text()
    assert "Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * Math.pow(2, attempt))" in src
    result = subprocess.run(
        [NODE, "--input-type=module", "-e",
         'const b=(a)=>Math.min(30000, 500*Math.pow(2,a));'
         'console.log(JSON.stringify([0,1,2,3,10].map(b)));'],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [500, 1000, 2000, 4000, 30000]


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(list(globals().items())):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - report and keep going
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - failed}/{total} passed")
    raise SystemExit(1 if failed else 0)
