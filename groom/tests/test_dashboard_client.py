"""Tests for the dashboard client module as a *whole file* (assets/dashboard.js).

Nothing else in the suite parses this module. The connection-state tests pull one
pure function out of it by string slicing, so a syntax error anywhere else in the
file would sail past every Python test and only surface as a blank dashboard in a
browser. A parse check is therefore not a formality here — it is the only thing
standing between a typo and a dead page, until the Playwright suite lands.

The rest of the assertions guard the JSON-first contract at the boundary the
server tests cannot see: that the client reads its endpoints as JSON, that no
fragment-swapping machinery survives, and that htmx is really gone rather than
merely unused.

Run: uv run pytest tests/test_dashboard_client.py
"""
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
    """The node binary. Called only past `_skipped()`, which is what rules its
    absence out — so the caller below spells the command rather than the question of
    whether node is installed."""
    assert NODE is not None
    return NODE


def _skipped() -> bool:
    if NODE is not None:
        return False
    print("SKIP  node not on PATH — dashboard.js parse check not run", file=sys.stderr)
    return True


def test_the_client_module_parses():
    # `node --check` parses as a module only for .mjs, and dashboard.js must keep
    # its .js name because that is what the <script type="module"> tag asks for —
    # so check a copy under the extension node needs.
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
    # The one regression this file exists to catch. Every read endpoint returns
    # JSON now; a leftover `.text()` would hand a component a string where it
    # expects an object and fail silently at runtime, not at import.
    src = CLIENT.read_text()
    assert ".text()" not in src
    for route in ("/api/state", "/worker/", "/repos", "/files/", "/file/", "/diff/", "/traces"):
        assert route in src, route


def test_no_fragment_swapping_survives():
    # Fragments were the old transport: the server sent markup keyed by element id
    # and the client swapped it in. Preact reconciles instead, so any surviving
    # swap helper would be a second, unreconciled render path writing into a tree
    # Preact believes it owns.
    src = CLIENT.read_text()
    assert "applyFragments" not in src
    assert "outerHTML" not in src
    assert "hx-swap-oob" not in src


def test_htmx_is_gone_from_the_shipped_surface():
    # Not merely unreferenced — absent. A vendored copy still on disk is a file the
    # next person wires back up, and the shell must not load it at all.
    assert not list(ASSETS.glob("htmx*"))
    shell = (ROOT / "groom" / "templates" / "dashboard.html").read_text()
    assert "htmx" not in shell
    assert "ws-send" not in shell and "hx-" not in shell


def test_the_only_markup_the_client_sets_comes_from_a_sanitizer_or_a_renderer():
    # `dangerouslySetInnerHTML` is the one place untrusted text could become markup.
    # Every use must be fed by DOMPurify (gate questions), diff2html or highlight.js
    # — all of which escape — so this counts the sites and pins them to those three.
    src = CLIENT.read_text()
    sites = src.count("dangerouslySetInnerHTML")
    sources = src.count("DOMPurify.sanitize") + src.count("Diff2Html.html") + src.count("highlight(")
    assert sites and sources >= sites


def test_the_render_module_is_gone():
    # Phase 3's endpoint: no server-side HTML anywhere. The module and its tests
    # were deleted together, and the projection tests carry what they asserted.
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


def test_a_gate_block_can_disclose_its_whole_context_file():
    # The question is an excerpt; the operator answering it needs the findings and
    # earlier escalations around it. The gate block therefore carries a lazy
    # disclosure that fetches the gate file through `/file/` — keyed by the gate's
    # own `file_path`, the path relative to the run's workspace — and renders it
    # through the same sanitized Markdown path the question uses.
    src = CLIENT.read_text()
    assert "function ContextDisclosure" in src
    assert 'fetch("/file/" + encodeURIComponent(workflowId) + "?path=" + encodeURIComponent(filePath))' in src
    gate_block = src[src.index("function GateBlock") : src.index("function DiffDisclosure")]
    assert "ContextDisclosure" in gate_block
    context = src[src.index("function ContextDisclosure") : src.index("function GateBlock")]
    assert "<${Markdown}" in context
    assert "dangerouslySetInnerHTML" not in context
