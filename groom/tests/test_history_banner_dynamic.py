from __future__ import annotations

import json
import re
import shlex
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import expect
from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _scan,
    teardown_module,  # noqa: F401
)
from test_history import refresh
from test_history_dynamic import _clear
from test_history_open_dynamic import AXE, DETAIL, _opened, _ready, _rich
from test_run_clock_dynamic import _stub_clipboard

from groom import docker_io, state, store
from groom.models import WorkflowContainer

BANNER = f"{DETAIL} #detail-ending"
ARGV = ["workhorse-coder", "run", "--resume-run", "/srv/runs/hist-a", "--cli", "codex", "--config", "/etc/coder.toml"]


@contextmanager
def _stopped(tmp_path: Path, terminal: str = "fail", argv: list[str] | None = ARGV, kept: bool = True, run_dir: str = "") -> Iterator[float]:
    now = time.time()
    _clear()
    _rich("hist-a", now - 3 * 3600, terminal, {"error.class": "WatchdogKilled", "progress": "1/2"})
    folder = tmp_path / "hist-a"
    if kept:
        folder.mkdir(parents=True)
        if argv is not None:
            (folder / "launch.json").write_text(json.dumps({"resume_argv": argv}))
    with store.STORE.writing() as conn:
        conn.execute("UPDATE spans SET run_dir = ? WHERE run_id = 'hist-a'", (run_dir or str(folder),))
    refresh(now)
    try:
        yield now
    finally:
        _clear()


def test_a_failed_runs_overview_starts_with_the_banner_and_a_successful_run_has_none(tmp_path):
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stopped(tmp_path):
        page = _opened(live)
        try:
            _ready(page)
            first = page.locator(f"{DETAIL} .ov > *").first.get_attribute("id")
            head = page.locator(f"{BANNER} h2").inner_text()
            text = page.locator(BANNER).inner_text()
        finally:
            page.close()
    with _stopped(tmp_path / "ok", "terminal"):
        page = _opened(live)
        try:
            _ready(page)
            none = page.locator(BANNER).count()
        finally:
            page.close()
    assert first == "detail-ending"
    assert head == "Ended at test: WatchdogKilled"
    assert "work item" in text
    assert none == 0


def test_the_link_opens_the_activity_tab_with_the_failing_row_selected_and_its_step_in_the_reading_pane(tmp_path):
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stopped(tmp_path):
        page = _opened(live)
        try:
            _ready(page)
            page.get_by_role("button", name="Open this moment in Activity").click()
            page.wait_for_selector(f"{DETAIL} .tl button.ev[aria-current=true]", timeout=15000)
            selected = page.locator(f"{DETAIL} .tl button.ev[aria-current=true]")
            tab = page.get_by_role("tab", name=re.compile("^Activity")).get_attribute("aria-selected")
            expect(page.locator(f"{DETAIL} .rd")).to_contain_text("test")
            kind = selected.get_attribute("data-entry") or ""
        finally:
            page.close()
    assert tab == "true"
    assert kind.startswith("failed:")


def test_the_banner_shows_the_recorded_command_and_the_copy_control_copies_it_and_says_copied(tmp_path):
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stopped(tmp_path):
        page = _opened(live)
        try:
            _ready(page)
            shown = page.locator(f"{BANNER} .ending-cmd").inner_text()
            _stub_clipboard(page, "ok")
            button = page.get_by_role("button", name="Copy command")
            button.focus()
            page.keyboard.press("Enter")
            expect(page.locator(BANNER).get_by_text("Copied", exact=True)).to_be_visible()
            copied = page.evaluate("() => window.__copied")
        finally:
            page.close()
    assert shown == shlex.join(ARGV)
    assert copied == [shlex.join(ARGV)]


def test_a_container_runs_banner_says_the_command_runs_inside_that_container(tmp_path):
    live = _live()
    assert live is not None, _UNAVAILABLE
    record = json.dumps({"resume_argv": ["workhorse-coder", "run", "--resume-run", "/runs/hist-a"], "container": True})
    mounted = patch.dict(state.WORKFLOWS, {"c1": WorkflowContainer(container_id="c1", name="coder", run_id="hist-a", runs_volume="runs-vol")})
    with mounted, patch.object(docker_io, "read_file", return_value=record), _stopped(tmp_path, kept=False, run_dir="/runs/hist-a"):
        page = _opened(live)
        try:
            _ready(page)
            text = page.locator(f"{BANNER} .ending-how").inner_text()
        finally:
            page.close()
    assert text.startswith("To continue it, run this inside the container it ran in: workhorse-coder run --resume-run /runs/hist-a")


def test_a_runs_banner_says_it_cannot_be_continued_when_its_folder_is_gone_and_shows_no_command(tmp_path):
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stopped(tmp_path, kept=False):
        page = _opened(live)
        try:
            _ready(page)
            text = page.locator(f"{BANNER} .ending-how").inner_text()
            copy = page.get_by_role("button", name="Copy command").count()
        finally:
            page.close()
    assert text == "This run's folder is gone, so it cannot be continued."
    assert copy == 0


def test_the_work_items_tile_of_an_ended_run_shows_the_cost_per_item_with_no_median_comparison(tmp_path):
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stopped(tmp_path):
        page = _opened(live)
        try:
            _ready(page)
            tile = page.locator(f"{DETAIL} #detail-items-tile").inner_text()
        finally:
            page.close()
    assert re.search(r"\$[\d.]+ per item", tile)
    assert "median" not in tile and "finished item" not in tile


def test_history_offers_no_stop_resume_or_rewind_control_on_a_stopped_run(tmp_path):
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stopped(tmp_path):
        page = _opened(live)
        try:
            _ready(page)
            names = page.locator(f"{DETAIL} button").evaluate_all("(buttons) => buttons.map((b) => (b.getAttribute('aria-label') || b.innerText).toLowerCase())")
        finally:
            page.close()
    assert not [name for name in names if re.search(r"\b(stop|resume|rewind)\b", name)]


def test_the_banner_passes_an_axe_scan_and_its_link_and_copy_control_work_from_the_keyboard(tmp_path):
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stopped(tmp_path):
        page = _opened(live)
        try:
            _ready(page)
            page.add_script_tag(path=str(AXE))
            found = _scan(page)
            link = page.get_by_role("button", name="Open this moment in Activity")
            link.focus()
            page.keyboard.press("Enter")
            page.wait_for_selector(f"{DETAIL} .tl button.ev[aria-current=true]", timeout=15000)
            region = page.locator(BANNER).count()
        finally:
            page.close()
    assert not found, json.dumps(found, indent=1)
    assert region == 0
