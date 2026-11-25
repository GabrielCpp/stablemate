from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ostler_qa_diagnostics import (
    DEFAULT_EVENTUALLY_TIMEOUT,
    EVENTUALLY_INTERVAL,
    CheckFailed,
)
from ostler_qa_http import ClaimFault, _not_yet, _sampled
from ostler_qa_resolve import QaResolve
from ostler_qa_tools import MaestroResult, ToolResult
from ostler_qa_verifiers import (
    VERIFIERS,
)


class QaChecks(QaResolve):
    """The assertions a scenario makes and the polling behind them."""

    def check(
        self,
        label: str,
        condition: Any,
        *,
        actual: Any = None,
        expected: Any = None,
        covers: Sequence[str] | None = None,
    ) -> bool:
        """Record one claim about behaviour."""
        return self._record(label, condition, actual, expected, covers)

    def require(
        self,
        label: str,
        condition: Any,
        *,
        actual: Any = None,
        expected: Any = None,
        covers: Sequence[str] | None = None,
    ) -> None:
        """Record one claim and stop the scenario when it does not hold."""
        if not self._record(label, condition, actual, expected, covers):
            raise CheckFailed(label)

    def eventually(
        self,
        label: str,
        condition: Callable[[], Any],
        *,
        timeout: float = DEFAULT_EVENTUALLY_TIMEOUT,
        interval: float = EVENTUALLY_INTERVAL,
        actual: Any = None,
        expected: Any = None,
        covers: Sequence[str] | None = None,
    ) -> bool:
        """Record one claim about behaviour that the page is allowed to arrive at."""
        if not callable(condition):
            raise TypeError(
                f"qa.eventually({label!r}, …) needs a callable to re-sample, and was handed "
                f"an already-evaluated {type(condition).__name__}. Python collapsed the read "
                "before this harness saw it, so there is nothing left to retry — hand over "
                "the sampler instead: wrap the expression you just wrote in a lambda "
                "(`lambda: page.text(\"#badge\")`), or pass a bound method "
                "(`badge.is_visible`) or a named nested function."
            )
        passed, polls, settled_ms = self._poll(condition, timeout, interval)
        return self._record(
            label,
            passed,
            _sampled(actual),
            expected,
            covers,
            extra={
                "mode": "eventually",
                "settled_ms": settled_ms,
                "timeout_ms": int(timeout * 1000),
                "polls": polls,
            },
        )

    def require_eventually(
        self,
        label: str,
        condition: Callable[[], Any],
        *,
        timeout: float = DEFAULT_EVENTUALLY_TIMEOUT,
        interval: float = EVENTUALLY_INTERVAL,
        actual: Any = None,
        expected: Any = None,
        covers: Sequence[str] | None = None,
    ) -> None:
        """`eventually`, stopping the scenario when the page never arrives."""
        if not self.eventually(
            label,
            condition,
            timeout=timeout,
            interval=interval,
            actual=actual,
            expected=expected,
            covers=covers,
        ):
            raise CheckFailed(label)

    def verify(
        self,
        check: str,
        observed: Any,
        *,
        covers: Sequence[str] | None = None,
        label: str = "",
        **args: Any,
    ) -> bool:
        """Make the observation an obligation's `verify:` bullet declares, and record it."""
        verifier = VERIFIERS.get(check)
        if verifier is None:
            raise ValueError(
                f"'{check}' is not a declared check — the vocabulary is: "
                f"{', '.join(sorted(VERIFIERS))}"
            )
        ran = observed if isinstance(observed, MaestroResult) else None
        if ran is not None:
            observed = ran.exit_code == 0
        verdict = verifier(observed, args)
        rendered = ", ".join(f"{key}={value!r}" for key, value in args.items())
        ending_fields = (
            {"command_ending": {"exit_code": observed.exit_code, "stderr": observed.stderr.strip()[-500:]}}
            if not verdict.passed and isinstance(observed, ToolResult) else {}
        )
        if not verdict.passed and ran is not None and ran.seen:
            ending_fields = {**ending_fields, "seen": ran.seen}
        return self._record(
            label or f"{check}({rendered})",
            verdict.passed,
            verdict.actual,
            verdict.expected,
            covers,
            extra={"check": check, "check_args": args, **ending_fields},
        )

    def holds(
        self,
        state: str,
        states: Mapping[str, Sequence[tuple[str, Any, Mapping[str, Any]]]],
        *,
        covers: Sequence[str] | None = None,
    ) -> bool:
        """Record whether the record read back is in `state`, and when it is not, name the sibling state it is in."""
        def matches(name: str) -> bool:
            return all(VERIFIERS[check](operand, args).passed for check, operand, args in states[name])

        if matches(state):
            return self._record(f"the record is in {state}", True, state, state, covers)
        holding = next((name for name in states if name != state and matches(name)), "")
        actual = holding or "no state of the lifecycle"
        return self._record(
            f"the record should be in {state}, and {holding + ' holds instead' if holding else 'no state of the lifecycle holds'}",
            False, actual, state, covers,
            extra={"state": state, "holds": holding},
        )

    def condition(
        self,
        state: str,
        page: str,
        states: Mapping[str, Sequence[tuple[str, Any, Mapping[str, Any]]]],
    ) -> None:
        """Hold the data state a claim is observed under, and stop the scenario with a fault of the book's when the read says it is not in it."""
        def matches(name: str) -> bool:
            return all(VERIFIERS[check](operand, args).passed for check, operand, args in states[name])

        if matches(state):
            self._held.append(state)
            self._recorder.emit({"type": "condition", "state": state, "held": True})
            self._exchange = None
            return
        holding = next((name for name in states if name != state and matches(name)), "")
        actual = holding or "no state of the lifecycle"
        self._claim_fault = ClaimFault("condition", state, page)
        _ = self._record(
            f"the condition should be {state}, and {holding + ' holds instead' if holding else 'no state of the lifecycle holds'}",
            False, actual, state, self.covers,
            extra={"state": state, "holds": holding},
        )
        raise CheckFailed(state)

    def _poll(
        self, condition: Callable[[], Any], timeout: float, interval: float
    ) -> tuple[bool, int, int]:
        """Re-sample `condition` until it holds or the deadline passes."""
        started = time.monotonic()
        polls = 0
        while True:
            polls += 1
            try:
                passed = bool(condition())
            except BaseException as exc:  # noqa: BLE001 — re-raised unless it means "not yet"
                if not _not_yet(exc):
                    raise
                passed = False
            elapsed = time.monotonic() - started
            if passed or elapsed >= timeout:
                return passed, polls, int(elapsed * 1000)
            time.sleep(min(interval, timeout - elapsed))
