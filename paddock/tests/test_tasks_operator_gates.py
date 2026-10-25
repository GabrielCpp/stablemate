"""The operator-gate watcher, over a stage that is one repo or a folder of repos."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fakes import DOCS, fake_run, folder_run

from paddock.tasks import operator_gates as og


def park(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("STATUS: AWAITING_OPERATOR\n", encoding="utf-8")


def watch_once(run, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    monkeypatch.setattr(og, "GATE_POLL_S", 0.0)
    monkeypatch.setattr(og, "GATE_GRACE_S", 0.0)
    stop = threading.Event()
    waits = iter([False, True])
    monkeypatch.setattr(stop, "wait", lambda _timeout: next(waits))
    og.watch_operator_gates(run, stop)
    return og.operator_gates_of(run)


def test_a_gate_in_a_single_repo_is_keyed_by_its_path_in_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = fake_run(tmp_path)
    park(run.stage / "docs" / "epics" / "e1" / "context.md")
    gates = watch_once(run, monkeypatch)
    assert [g["gate"] for g in gates] == ["docs/epics/e1/context.md"]


def test_a_gate_in_any_repo_of_a_folder_is_keyed_from_the_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = folder_run(tmp_path)
    park(run.stage / DOCS / "docs" / "epics" / "e1" / "context.md")
    park(run.stage / "web-app" / "context.md")
    gates = watch_once(run, monkeypatch)
    assert sorted(g["gate"] for g in gates) == [
        f"{DOCS}/docs/epics/e1/context.md",
        "web-app/context.md",
    ]
