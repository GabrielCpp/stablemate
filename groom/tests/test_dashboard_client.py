"""Tests for the dashboard client module as a *whole file* (assets/dashboard.js)."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "groom" / "assets"
CLIENT = ASSETS / "dashboard.js"
NODE = shutil.which("node")


def _node() -> str:
    """The node binary."""
    assert NODE is not None
    return NODE


def _skipped() -> bool:
    if NODE is not None:
        return False
    print("SKIP  node not on PATH — dashboard.js parse check not run", file=sys.stderr)
    return True


def test_the_client_module_parses():
    if _skipped():
        return
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "dashboard.mjs"
        copy.write_text(CLIENT.read_text())
        result = subprocess.run(
            [_node(), "--check", str(copy)], capture_output=True, text=True, timeout=30
        )
    assert result.returncode == 0, result.stderr


def test_every_endpoint_is_read_as_json():
    src = CLIENT.read_text()
    assert ".text()" not in src
    for route in ("/api/state", "/worker/", "/files/", "/file/", "/diff/"):
        assert route in src, route


def test_no_fragment_swapping_survives():
    src = CLIENT.read_text()
    assert "applyFragments" not in src
    assert "outerHTML" not in src
    assert "hx-swap-oob" not in src


def test_htmx_is_gone_from_the_shipped_surface():
    assert not list(ASSETS.glob("htmx*"))
    shell = (ROOT / "groom" / "templates" / "dashboard.html").read_text()
    assert "htmx" not in shell
    assert "ws-send" not in shell and "hx-" not in shell


def test_the_only_markup_the_client_sets_comes_from_a_sanitizer_or_a_renderer():
    src = CLIENT.read_text()
    sites = src.count("dangerouslySetInnerHTML")
    sources = src.count("DOMPurify.sanitize") + src.count("Diff2Html.html") + src.count("highlight(")
    assert sites and sources >= sites


def test_the_render_module_is_gone():
    assert not (ROOT / "groom" / "render.py").exists()
    assert not (ROOT / "tests" / "test_render.py").exists()
    for py in (ROOT / "groom").rglob("*.py"):
        assert "from groom import render" not in py.read_text(), py


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


def test_closing_the_detail_keeps_the_run_filter():
    src = CLIENT.read_text()
    close = src[src.index("function closeDetail") : src.index("/** A pushed refresh")]
    assert 'sendWatch("")' in close
    assert "query" not in close


def test_the_detail_tabs_are_a_tablist_with_a_labelled_panel():
    src = CLIENT.read_text()
    assert 'role="tablist"' in src
    assert 'role="tabpanel"' in src
    assert 'aria-label="Close run detail"' in src
    assert 'aria-label="Open gates"' in src


def test_the_overview_marks_waiting_in_words_and_never_prints_a_blank_cost():
    src = CLIENT.read_text()
    assert "the operator" in src
    assert "\"waiting on \"" in src
    assert "reports no cost" in src


def test_a_gate_block_shows_questions_without_a_context_disclosure():
    src = CLIENT.read_text()
    gate_block = src[src.index("function GateBlock") : src.index("function GateStrip")]
    assert 'source=${gate.question}' in gate_block
    assert "ContextDisclosure" not in src
    assert "Full context" not in src


def test_a_rejected_answer_frame_is_toasted_as_text():
    src = CLIENT.read_text()
    on_frame = src[src.index("function onFrame") : src.index("export function sendWatch")]
    assert 'msg.type === "answer_rejected"' in on_frame
    handler = src[src.index("function onAnswerRejected") :]
    handler = handler[: handler.index("\n}\n")]
    assert "pushToast(" in handler and "msg.reason" in handler
    assert "innerHTML" not in handler


def test_the_overview_refetches_only_when_the_pushed_revision_moves():
    src = CLIENT.read_text()
    overview = src[src.index("function Overview") : src.index("function DetailsTab")]
    assert "detail.figures_rev" in overview
    assert "setInterval" not in overview
    assert "aria-live" not in src[src.index("function CostTile") : src.index("function DetailsTab")]


def test_the_cost_tile_ticks_in_the_browser_every_second():
    src = CLIENT.read_text()
    tick = src[src.index("function useSecondTick") : src.index("function timeCell")]
    assert "setInterval" in tick and "1000" in tick
    tile = src[src.index("function CostTile") : src.index("function FlowRows")]
    assert "useSecondTick()" in tile


def test_a_run_row_prints_its_figures_in_words_and_keeps_the_coverage_when_narrowed():
    src = CLIENT.read_text()
    figures = src[src.index("function RowFigures") : src.index("function RunRow")]
    assert "no cost yet" in figures
    assert "no cost reported" in figures
    assert "figures.priced_turns" in figures and "figures.turns" in figures
    assert "items_total" in figures
    assert "narrow=${Boolean(selected)}" in src
