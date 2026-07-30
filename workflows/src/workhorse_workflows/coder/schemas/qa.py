"""The QA flow's models — the running verdict, and what each deterministic gate returns.

**`QaResult` is one model for what the YAML kept as one key.** Nine nodes wrote
`qa_result` — the ostler runner, the evidence gate, the sentinel gate, the regression
suite, three `mark-*` scripts and three agent turns — with three different payload shapes,
because a run-context key has no schema. Here it is a single model whose `ostler` field is
simply empty for the nodes that never had a payload, and it is what the flow threads from
gate to gate as *the* verdict. Collapsing it is not a narrowing: every writer already
produced `status` and `notes`, and only the ostler-backed ones produced more.

**The status vocabularies stay separate.** `QaResult.status` is ostler's four-state
`passed | failed | blocked | invalid`; `QaPlanValidation.status` is the two-state
`passed | invalid` the validator computes for itself off a returncode. They looked alike as
untyped dicts and routed through different branch tables; they are different types here.

The `qa_cleared`, `stack_*`, `backlog_items_*` and `screenshots_*` keys were flat scalars
sprayed into the run context — six of them for `ensure-stack.py` alone. Each script's set
becomes one model, because the set is what the script actually returns.
"""
from __future__ import annotations

from typing import Any

from workhorse_workflows.coder.schemas._base import CoderResult


class QaResult(CoderResult):
    """The story's running QA verdict — ostler's four states, plus the blank before one.

    `status` starts empty rather than at `invalid`: the flow reads it before anything has
    run (`plan_qa` is handed the previous pass's notes, and `setup_fix` can be reached
    before the runner ever executes), and an unrun gate is not a failed one. Every branch
    that routes on it names its arms explicitly and sends the blank to a `default`, which
    is what the YAML's branch tables did.

    `ostler` carries the runner's raw payload. It is empty for the writers that never had
    one — the sentinel gate, the evidence gate, the agent repair turns.
    """

    status: str = ""
    notes: str = ""
    ostler: dict[str, Any] = {}


class QaPlanValidation(CoderResult):
    """`ostler qa validate` — is the authored `qa-plan.yml` a plan the runner can execute?

    Two states only, and `invalid` is the default for the same reason `OkfContextResult`
    uses it: the script computed the verdict from a returncode rather than reading it off
    ostler, so a missing answer is a failure to validate, not a pass.
    """

    status: str = "invalid"
    notes: str = ""
    ostler: dict[str, Any] = {}


class QaCleared(CoderResult):
    """`clear-qa-evidence.py` — the stale `qa/` outputs and root verdict are gone.

    The script's `{"qa_cleared": "yes"}` was unconditional: it printed the same string
    whether it deleted two artifacts or found no spec dir at all. `cleared` is `False` on
    that second path, so the run record distinguishes "nothing to clear" from "cleared" —
    nothing branches on it either way, exactly as before.
    """

    cleared: bool = False


class StackStatus(CoderResult):
    """`ensure-stack.py` — the durable QA stack is up, adopted, absent, or broken.

    `ready` is three-state on purpose. `skip` (no manifest authored) is not a failure and
    routes exactly where `yes` does; only `no` reaches the setup-repair loop.

    The pids are strings because `workhorse.stack.ensure_stack` returns them that way —
    they are recorded for a human killing a leaked stack, never arithmetic.
    """

    ready: str = "no"
    app_pid: str = ""
    app_pgid: str = ""
    entry_url: str = ""
    failed_step: str = ""
    notes: str = ""


class BacklogDrain(CoderResult):
    """`append-backlog-item.py` — the coder→author edge, drained into `docs/backlog.md`.

    Both counts are reported and neither is routed on: the filer is best-effort by design,
    and an unwritable backlog degrades to `appended=0` with the items file kept rather than
    failing the story.
    """

    appended: int = 0
    skipped: int = 0
    notes: str = ""


class ScreenshotFlush(CoderResult):
    """`flush-root-screenshots.py` — stray root images relocated into `<spec_dir>/qa/`.

    `kept_tracked` is the count left alone because git already tracks them: a tracked root
    image is a committed asset, not QA litter.
    """

    flushed: int = 0
    kept_tracked: int = 0
    notes: str = ""


class RegressionPlatform(CoderResult):
    """`detect-regression-platform.py` — which committed suites, if any, this plan touched.

    `platform` defaults to `none` because the script fails **open**: an unreadable
    plan-context skips the regression step rather than blocking a story that may not have a
    UI at all. That is the opposite default from every gate in this module, and deliberate —
    this is a router, not a verdict.
    """

    platform: str = "none"
    layers: list[str] = []
    paths: list[str] = []


class FailureAttribution(CoderResult):
    """Which OKF node, if any, claims to verify a failing regression test.

    Diagnostic only. `classification` is `impacted` (a node this story changed verifies
    it), `outside-impact` (some other node does) or `unattributed` (the OKF
    `verificationIndex` names no owner) — and none of the three weakens the gate: a
    regression failure is the story's fix work whichever bucket it lands in.
    """

    test: str = ""
    path: str = ""
    classification: str = ""
    nodes: list[str] = []


class RegressionRun(CoderResult):
    """`run-regression-suite.py` — the committed journey suites' own verdict.

    `status` defaults to `passed`, which reads wrong for a gate until you see what the
    script means by it: every "nothing to run" path — no Makefile, no `e2e-journeys`
    target, no `maestro_flows/`, an unknown platform — is a *skip*, and a skip is `passed`.
    A repo with no regression suite is not a repo that failed one. Only a real non-zero
    suite exit is `failed`, and only an unreachable stack or emulator is `blocked`.

    The script emitted this twice — once as `regression_run` and once, status and notes
    only, as `qa_result` — so the shared `blocked → setup_fix` loop would pick it up.
    `as_qa_result()` is that mirror, made explicit and defined once.
    """

    status: str = "passed"
    failing_tests: list[str] = []
    log_path: str = ""
    notes: str = ""
    failure_attribution: list[FailureAttribution] = []

    def as_qa_result(self) -> QaResult:
        """The story's running verdict, as the YAML's duplicated `qa_result` key had it."""
        return QaResult(status=self.status, notes=self.notes)


__all__ = [
    "BacklogDrain",
    "FailureAttribution",
    "QaCleared",
    "QaPlanValidation",
    "QaResult",
    "RegressionPlatform",
    "RegressionRun",
    "ScreenshotFlush",
    "StackStatus",
]
