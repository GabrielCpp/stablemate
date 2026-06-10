"""Tests for resilient template rendering: a missing variable or an attribute read
on a wrong-typed value (a common upstream-LLM-output failure mode) renders as empty
instead of raising and killing the run — while still logging a warning so the bad
reference stays visible.

Run: ./.venv/bin/python tests/test_templates_resilient.py   (or via pytest)
"""
from __future__ import annotations

import logging

from workhorse.templates import render_string


def test_attribute_on_wrong_typed_value_renders_empty():
    # The reported crash: qa_result came back as a bare string, but the node arg
    # reads `{{ qa_result.notes }}`. Must degrade to empty, not raise.
    out = render_string("notes={{ qa_result.notes }}", {"qa_result": "failed"})
    assert out == "notes="


def test_missing_top_level_var_renders_empty():
    assert render_string("x={{ nope }}", {}) == "x="


def test_deep_chain_through_missing_renders_empty():
    # ChainableUndefined: a.b.c where a is missing must not explode mid-path.
    assert render_string("v={{ a.b.c }}", {}) == "v="


def test_valid_reference_still_renders():
    out = render_string("{{ qa_result.notes }}", {"qa_result": {"notes": "fix the test"}})
    assert out == "fix the test"


def test_undefined_use_is_logged():
    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    logger = logging.getLogger("workhorse.templates")
    h = _Capture()
    logger.addHandler(h)
    try:
        render_string("{{ qa_result.notes }}", {"qa_result": "failed"})
    finally:
        logger.removeHandler(h)
    assert any("notes" in m for m in records), f"expected a warning, got {records}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
