"""How long a verdict takes: in-process, and as the process the agent launches on every call."""

from __future__ import annotations

import json
import subprocess
import sys
import time

from saddlebag import guard

PAYLOADS = [
    {"tool_name": "Bash", "tool_input": {"command": "cat .env | grep X && printenv HOME; aws secretsmanager get-secret-value --secret-id x"}},
    {"tool_name": "Bash", "tool_input": {"command": "set -euo pipefail; git status --short && ls -la src"}},
    {"tool_name": "Read", "tool_input": {"file_path": "/home/u/project/README.md"}},
    {"tool_name": "Read", "tool_input": {"file_path": ".env"}},
]


def wall(argv: list[str], payload: str = "") -> float:
    start = time.perf_counter()
    subprocess.run(argv, input=payload, text=True, capture_output=True, check=True)
    return time.perf_counter() - start


def test_decide_averages_under_a_millisecond() -> None:
    start = time.perf_counter()
    for i in range(200):
        guard.decide(PAYLOADS[i % len(PAYLOADS)])
    assert (time.perf_counter() - start) / 200 < 0.001


def test_the_hook_process_adds_under_fifty_milliseconds_to_interpreter_start() -> None:
    payload = json.dumps(PAYLOADS[0])
    program = "from saddlebag.cli import main; main(['guard','--hook'])"
    floor = min(wall([sys.executable, "-c", "pass"]) for _ in range(15))
    hook = min(wall([sys.executable, "-c", program], payload) for _ in range(15))
    print(f"interpreter floor {floor * 1000:.1f} ms, guard hook {hook * 1000:.1f} ms")
    assert hook - floor < 0.05
