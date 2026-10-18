from __future__ import annotations

import _attend_support as at
import _tui_support as support
import pytest

from groom import state
from groom.tui import store as client


@pytest.fixture(autouse=True)
def _groom(tmp_path, monkeypatch):
    at.isolate(tmp_path, monkeypatch, "session")
    support.seed()
    yield
    state.WORKFLOWS.clear()
    at.release()


def test_apply_state_keeps_the_attend_summary_projection_built():
    at.begin("j-1", "run-blocked", session="s-1", started_at=at.T0)
    at.end("j-1", 0, "blocked", at.T0 + 5)
    store = client.apply_state(client.Store(), support.state_frame())
    assert store.attend["mode"] == "session"
    assert store.attend["rev"] == at.T0 + 5
    assert store.attend["by_run"]["run-blocked"]["session_id"] == "s-1"
    assert store.attend["by_run"]["run-blocked"]["status"] == "completed"


def test_a_state_frame_without_attend_keeps_the_last_one():
    at.begin("j-1", "run-blocked", session="s-1")
    store = client.apply_state(client.Store(), support.state_frame())
    frame = {key: value for key, value in support.state_frame().items() if key != "attend"}
    assert client.apply_state(store, frame).attend == store.attend


def test_the_attendant_of_the_selected_run_comes_from_its_run_id():
    at.begin("j-1", "run-blocked", session="s-1")
    store = client.select(client.apply_state(client.Store(), support.state_frame()), support.ACME)
    assert (client.selected_attendant(store) or {})["job_id"] == "j-1"
    assert client.selected_attendant(client.select(store, support.GLOBEX)) is None
    assert client.selected_attendant(client.select(store, "missing")) is None
