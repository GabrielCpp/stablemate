from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from groom.tui import connection

ASSETS = Path(__file__).resolve().parents[1] / "groom" / "assets"
NODE = shutil.which("node")

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

NOW = 1_000_000
OBSERVATIONS = [
    {"now": NOW, "socketOpen": True, "lastMessageTs": NOW, "closedSince": 0},
    {"now": NOW, "socketOpen": True, "lastMessageTs": NOW - 4_000, "closedSince": 0},
    {"now": NOW, "socketOpen": True, "lastMessageTs": NOW - 15_000, "closedSince": 0},
    {"now": NOW, "socketOpen": True, "lastMessageTs": NOW - 15_001, "closedSince": 0},
    {"now": NOW, "socketOpen": True, "lastMessageTs": NOW - 90_000, "closedSince": 0},
    {"now": NOW, "socketOpen": False, "lastMessageTs": NOW - 30_000, "closedSince": NOW - 10_000},
    {"now": NOW, "socketOpen": False, "lastMessageTs": 0, "closedSince": NOW - 60_000},
    {"now": NOW, "socketOpen": False, "lastMessageTs": 0, "closedSince": NOW - 60_001},
    {"now": NOW, "socketOpen": False, "lastMessageTs": 0, "closedSince": NOW - 600_000},
]


def _python(observations: list[dict]) -> list[dict]:
    return [
        {"phase": result.phase, "resyncing": result.resyncing}
        for result in (
            connection.derive_connection(connection.Observation(
                now=obs["now"],
                socket_open=obs["socketOpen"],
                last_message_ts=obs["lastMessageTs"],
                closed_since=obs["closedSince"],
            ))
            for obs in observations
        )
    ]


def _javascript(observations: list[dict]) -> list[dict]:
    assert NODE is not None
    harness = _HARNESS.format(path=json.dumps(str(ASSETS / "dashboard.js")))
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", harness],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "GROOM_OBS": json.dumps(observations)},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_python_machine_matches_the_dashboards_on_every_observation():
    if NODE is None:
        print("SKIP  node not on PATH — connection parity not exercised", file=sys.stderr)
        return
    assert _python(OBSERVATIONS) == _javascript(OBSERVATIONS)


def test_the_thresholds_equal_the_dashboards_constants():
    src = (ASSETS / "dashboard.js").read_text()
    stale = re.search(r"^export const STALE_AFTER_MS = (\d+);$", src, re.M)
    offline = re.search(r"^export const OFFLINE_AFTER_MS = (\d+);$", src, re.M)
    assert stale and offline
    assert connection.STALE_AFTER_MS == int(stale.group(1))
    assert connection.OFFLINE_AFTER_MS == int(offline.group(1))


def test_the_phases_follow_the_four_state_table():
    phases = _python(OBSERVATIONS)
    assert [p["phase"] for p in phases] == [
        "live", "live", "live", "stale", "stale",
        "reconnecting", "reconnecting", "offline", "offline",
    ]
    assert [p["resyncing"] for p in phases] == [False, False, False, True, True, True, True, True, True]


def test_backoff_doubles_from_half_a_second_and_caps_at_thirty():
    assert [connection.backoff_delay(n) for n in (0, 1, 2, 3, 10)] == [0.5, 1.0, 2.0, 4.0, 30.0]
