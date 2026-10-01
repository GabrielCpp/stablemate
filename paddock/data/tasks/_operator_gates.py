"""The operator-gate ledger, and the watcher that parks a round on a gate nothing answered."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from paddock import Run
from workhorse.pyflow.park import answered as gate_answered

logger = logging.getLogger(__name__)


GATE_POLL_S = 5.0

GATE_GRACE_S = 120.0


def operator_gates_path(run: Run) -> Path:
    return run.stage / "artifacts" / "build" / "operator-gates.json"


def operator_gates_of(run: Run) -> list[dict[str, Any]]:
    path = operator_gates_path(run)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def record_gate(run: Run, entry: dict[str, Any]) -> None:
    """Append one operator-gate outcome to its own ledger."""
    entries = operator_gates_of(run)
    entries.append(entry)
    run.write_json(operator_gates_path(run), entries)


def record_hand_answer(run: Run, gate: str, note: str, commit: str = "") -> None:
    """Record that a *person* answered a gate on this round, outside the harness."""
    entry: dict[str, Any] = {"gate": gate, "action": "hand", "note": note}
    if commit:
        entry["commit"] = commit
    record_gate(run, entry)


GATE_GLOBS = ("*context*.md", "docs/**/*context*.md")


def parked_gates(repo: Path) -> list[Path]:
    """Every context file currently sitting on `STATUS: AWAITING_OPERATOR`."""
    found = {path for glob in GATE_GLOBS for path in repo.glob(glob)}
    return sorted(p for p in found if p.is_file() and not gate_answered(p))


def watch_operator_gates(run: Run, stop: threading.Event) -> None:
    """Watch the produced repo for a stalled gate and park the round on it."""
    parked = {str(e["gate"]) for e in operator_gates_of(run)}
    first_seen: dict[str, float] = {}

    while not stop.wait(GATE_POLL_S):
        awaiting = set()
        for path in parked_gates(run.repo):
            gate = str(path.relative_to(run.repo))
            awaiting.add(gate)
            if gate in parked:
                continue
            since = first_seen.setdefault(gate, time.monotonic())
            if time.monotonic() - since < GATE_GRACE_S:
                continue
            parked.add(gate)
            record_gate(run, {"gate": gate, "action": "parked",
                              "reason": "still awaiting an operator "
                                        f"{GATE_GRACE_S / 60:.0f} minutes after it opened, "
                                        "and this round has no operator"})
            logger.warning("operator gate parked: %s", gate)
        for gate in set(first_seen) - awaiting:
            logger.info(
                "operator gate cleared after %.0fs of the %.0fs grace: %s",
                time.monotonic() - first_seen[gate], GATE_GRACE_S, gate,
            )
            del first_seen[gate]


def gates_watched(run: Run, phase: str) -> tuple[threading.Event, threading.Thread]:
    """Run `phase` with the gate watcher alive, and make sure it dies with the phase."""
    stop = threading.Event()
    thread = threading.Thread(
        target=watch_operator_gates, args=(run, stop),
        name=f"gate-watcher-{phase}", daemon=True,
    )
    return stop, thread
