"""A value a scenario captures lands on the run ledger, under the step it ran in, so the report can cite it."""

from __future__ import annotations

import json
from pathlib import Path

from ostler.qa.drivers import PythonDriver
from ostler.qa.session import QaSession


def _driver(repo: Path, secrets: dict[str, str] | None = None) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(json.dumps({"featuresRoot": "docs/features"}), encoding="utf-8")
    session = QaSession.create(spec, "qa-capture-1", "story-1", {}, secret_values=secrets)
    return PythonDriver(session, "cli", {"driver": "cli"}, root=repo, variables={})


def _ledger(repo: Path) -> list[dict[str, object]]:
    log = repo / "docs/specs/story-1/qa/qa-run.ndjson"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _captures(repo: Path) -> list[dict[str, object]]:
    return [record for record in _ledger(repo) if record.get("kind") == "capture"]


def _passed() -> dict[str, object]:
    return {"type": "scenario", "id": "s-1", "status": "passed", "assertions": 0, "failures": 0}


def test_a_capture_inside_a_step_lands_on_the_ledger_with_its_scenario_and_step(repo: Path) -> None:
    driver = _driver(repo)
    records = [
        {"type": "capture", "key": "tenant", "value": "acme"},
        {"type": "step_start", "id": "s-1-step-1", "label": "create the link"},
        {"type": "capture", "key": "link_id", "value": "lnk-42"},
        {"type": "step_end", "id": "s-1-step-1", "label": "create the link"},
        _passed(),
    ]

    _ = driver._grade("s-1", [], records, "", 0, timed_out=False)

    captures = [
        {key: record.get(key) for key in ("scenario", "key", "value", "step", "step_label")}
        for record in _captures(repo)
    ]
    assert captures == [
        {"scenario": "s-1", "key": "tenant", "value": "acme", "step": None, "step_label": None},
        {"scenario": "s-1", "key": "link_id", "value": "lnk-42", "step": "s-1-step-1", "step_label": "create the link"},
    ]
    assert driver.session.get_capture("link_id") == "lnk-42"


def test_a_captured_secret_is_redacted_on_the_ledger(repo: Path) -> None:
    driver = _driver(repo, secrets={"api_token": "tok-SECRET-9"})
    records = [{"type": "capture", "key": "auth", "value": "Bearer tok-SECRET-9"}, _passed()]

    _ = driver._grade("s-1", [], records, "", 0, timed_out=False)

    [capture] = _captures(repo)
    assert "tok-SECRET-9" not in json.dumps(capture)
    assert capture["value"] == "Bearer [REDACTED]"
