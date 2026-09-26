"""Tests for kit.qa.runner.bring_up_failure — which side a failed bring-up sends the repair to."""
from __future__ import annotations

from ostler.qa import stack

from workhorse_workflows.kit.qa.runner import bring_up_failure

RUNBOOK = "docs/features/api/ops/links-local.md"


def test_a_missing_health_route_is_the_apps_to_implement():
    error = (
        f"http://127.0.0.1:18081/healthz answered HTTP 404: the app is up and "
        f"{stack.ROUTE_MISSING} /healthz."
    )

    note = bring_up_failure("launch", error, RUNBOOK)

    assert "it must implement a health route" in note
    assert f"`health-path` in the runbook at `{RUNBOOK}`" in note
    assert "seed recipe" not in note


def test_any_other_failure_is_the_runbooks_to_repair():
    note = bring_up_failure("launch", "the launch command exited with code 2 during startup", RUNBOOK)

    assert note == (
        "Stack bring-up failed at step 'launch': the launch command exited with code 2 during "
        f"startup. Repair the runbook at `{RUNBOOK}` or its seed recipe (never background the "
        "stack in the agent shell)."
    )
