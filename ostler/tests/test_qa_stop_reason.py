"""A crashed scenario's recorded error names its stop line and exception, not the whole Python stack."""

from __future__ import annotations

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")


def _crash(exc: BaseException) -> BaseException:
    try:
        raise exc
    except BaseException as caught:  # noqa: BLE001 - the test inspects any raised exception
        return caught


def test_reason_names_plan_line_source_and_exception() -> None:
    exc = _crash(TimeoutError("Locator.click: Timeout 30000ms exceeded."))
    reason = harness.stop_reason(exc, __file__)
    assert "raise exc" in reason
    assert reason.startswith("line ")
    assert reason.endswith("; TimeoutError: Locator.click: Timeout 30000ms exceeded.")
    assert "Traceback" not in reason


def test_reason_without_plan_frame_is_the_exception_alone() -> None:
    exc = _crash(ValueError("bad"))
    assert harness.stop_reason(exc, "/nowhere/plan.py") == "ValueError: bad"


def test_empty_message_is_the_type_name() -> None:
    assert harness.stop_reason(_crash(KeyError()), "/nowhere/plan.py") == "KeyError"


def test_multiline_message_keeps_first_three_non_blank_lines() -> None:
    message = "Locator.click: Timeout.\n\nCall log:\n  - waiting for it\n  - fourth\n  - fifth"
    reason = harness.stop_reason(_crash(TimeoutError(message)), "/nowhere/plan.py")
    assert reason == "TimeoutError: Locator.click: Timeout. Call log: - waiting for it"


def test_long_message_is_capped_at_600_characters() -> None:
    reason = harness.stop_reason(_crash(RuntimeError("x" * 5000)), "/nowhere/plan.py")
    assert len(reason) == 600
    assert reason.endswith("…")
