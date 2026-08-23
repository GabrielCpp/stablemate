"""The per-criterion report a reviewer reads instead of the ledger.

Each test pins one thing the report must say — or refuse to say — for a person deciding
whether the run can be trusted: the verdict per criterion, which step earned it, what was
observed, and the warnings that name what was never looked at. The rendering is
deterministic, so the tests read the markdown as text and the data as a dict.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ostler.qa.evidence_map import build_evidence_map
from ostler.qa.report import (
    REPORT_FILE,
    ReportError,
    build_report,
    render_report,
    report_path,
    run_id_of,
    write_report,
)

CONTRACT = "okf:docs/features/orders/publish.md:contract"
DECLARED = 'conflict_on_stale(subject="manifest", token="etag")'


def _spec(
    tmp_path: Path,
    *,
    log: list[dict[str, Any]],
    criteria: list[dict[str, Any]] | None = None,
    obligations: list[dict[str, Any]] | None = None,
    context: bool = True,
    evidence: dict[str, Any] | None = None,
    qa_dirname: str = "qa",
) -> Path:
    spec = tmp_path / "docs/specs/story-1"
    (spec / qa_dirname).mkdir(parents=True, exist_ok=True)
    if context:
        (spec / "qa-okf-context.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "available": True,
                    "acceptanceCriteria": criteria or [],
                    "obligations": obligations or [],
                }
            ),
            encoding="utf-8",
        )
    (spec / qa_dirname / "qa-run.ndjson").write_text(
        "".join(json.dumps(record) + "\n" for record in log), encoding="utf-8"
    )
    (spec / qa_dirname / "run-manifest.json").write_text(
        json.dumps({"runId": "qa-run-1", "artifacts": []}), encoding="utf-8"
    )
    if evidence is not None:
        (spec / "qa-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    return spec


def _criterion(identifier: str, requirement: str) -> dict[str, Any]:
    return {"id": identifier, "requirement": requirement, "kind": "behavioral"}


def _start(run_id: str = "qa-run-1") -> dict[str, Any]:
    return {"kind": "session_start", "run_id": run_id, "story": "story-1", "ts": "2026-08-22T10:00:00Z"}


def _stop(status: str = "passed") -> dict[str, Any]:
    return {"kind": "session_stop", "run_id": "qa-run-1", "status": status, "ts": "2026-08-22T10:01:00Z"}


def _scenario_start(scenario: str, *covers: str, target: str = "api") -> dict[str, Any]:
    return {
        "kind": "scenario_start",
        "scenario": scenario,
        "target": target,
        "driver": "python",
        "mechanism": "live",
        "covers": list(covers),
    }


def _scenario_stop(scenario: str, status: str = "passed", **extra: Any) -> dict[str, Any]:
    return {"kind": "scenario_stop", "scenario": scenario, "status": status, **extra}


def _assert(
    scenario: str,
    number: int,
    label: str,
    *covers: str,
    result: str = "PASS",
    actual: Any = 200,
    expected: Any = 200,
    step: tuple[str, str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "kind": "assert",
        "id": f"{scenario}-{number}",
        "label": label,
        "check": "scenario_check",
        "params": {"passed": result == "PASS", "actual": actual, "expected": expected},
        "raw_result_file": f"/abs/{scenario}-{number}.json",
        "result": result,
        "driver": "python",
        "scenario": scenario,
        "action": number,
        "covers": list(covers),
        **extra,
    }
    if step:
        record["step"], record["step_label"] = step
    return record


def _step(scenario: str, step_id: str, label: str, *, exit_code: int = 0, **extra: Any) -> dict[str, Any]:
    return {"kind": "step", "id": step_id, "label": label, "cmd": "", "exit_code": exit_code, "driver": "python", "scenario": scenario, **extra}


def _screenshot(scenario: str, name: str, step: tuple[str, str] | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {"kind": "screenshot", "path": f"qa/screenshots/{name}.png", "sha256": "x", "bytes": 1, "scenario": scenario}
    if step:
        record["step"], record["step_label"] = step
    return record


STEP_ONE = ("s-step-1", "sign in with the provisioned account")
STEP_TWO = ("s-step-2", "fetch the page tree")


def _stamped_log() -> list[dict[str, Any]]:
    return [
        _start(),
        _scenario_start("s", "ac:1", "ac:2"),
        _assert("s", 1, "sign-in responds 200", "ac:1", step=STEP_ONE),
        _screenshot("s", "after-sign-in", step=STEP_ONE),
        _step("s", *STEP_ONE),
        _assert("s", 2, "the tree has a root", "ac:2", actual=[{"id": "p1"}], expected=None, step=STEP_TWO),
        _step("s", *STEP_TWO),
        _assert("s", 3, "tidy-up succeeded", actual="ok", expected="ok"),
        _scenario_stop("s", assertions=3, failures=0),
        _stop(),
    ]


def _video(target: str = "web", *, start_ms: int = 8000, duration: float = 20.0) -> dict[str, Any]:
    return {
        "kind": "video",
        "path": f"qa/videos/{target}.mp4",
        "target": target,
        "mode": "window",
        "actionStartOffsetMs": start_ms,
        "actionEndOffsetMs": start_ms + int(duration * 1000),
        "durationSeconds": duration,
        "width": 1440,
        "height": 900,
        "fps": 30.0,
    }


def _recorded_log() -> list[dict[str, Any]]:
    return [
        _start(),
        _scenario_start("s", "ac:1", target="web"),
        _step("s", *STEP_ONE, started_offset_ms=10_400, ended_offset_ms=12_900),
        _assert("s", 1, "the landing page shows the tree", "ac:1", step=STEP_TWO),
        _step("s", *STEP_TWO, started_offset_ms=12_900, ended_offset_ms=13_250),
        _scenario_stop("s", assertions=1, failures=0),
        _video(),
        _stop(),
    ]


# ----------------------------------------------------------------------------- verdicts


def test_a_criterion_is_pass_when_an_assertion_covering_it_passed(tmp_path: Path) -> None:
    spec = _spec(tmp_path, log=_stamped_log(), criteria=[_criterion("ac:1", "Sign in works."), _criterion("ac:2", "Tree loads.")])
    data = build_report(spec)
    by_id = {row["id"]: row for row in data["criteria"]}
    assert by_id["ac:1"]["verdict"] == "PASS"
    assert by_id["ac:2"]["verdict"] == "PASS"
    assert data["status"] == "passed"
    assert data["runId"] == "qa-run-1"
    assert data["counts"] == {
        "assertions": 3, "passed": 3, "failed": 0, "sentinelsFailed": 0,
        "scenarios": 1, "scenariosPassed": 1, "scenariosFailed": 0, "aborted": 0,
    }


def test_a_criterion_is_fail_when_any_assertion_covering_it_failed(tmp_path: Path) -> None:
    log = [
        _start(),
        _scenario_start("s", "ac:1"),
        _assert("s", 1, "first look passes", "ac:1"),
        _assert("s", 2, "second look fails", "ac:1", result="FAIL", actual=500),
        _scenario_stop("s", "failed", assertions=2, failures=1),
        _stop("failed"),
    ]
    spec = _spec(tmp_path, log=log, criteria=[_criterion("ac:1", "Sign in works.")])
    data = build_report(spec)
    assert data["criteria"][0]["verdict"] == "FAIL"
    text = render_report(data)
    assert "### ac:1 — FAIL" in text
    assert "| `500` | `200` | ✗ FAIL |" in text


def test_a_criterion_nothing_covers_is_unproven_and_warned(tmp_path: Path) -> None:
    spec = _spec(tmp_path, log=_stamped_log(), criteria=[_criterion("ac:9", "Nobody looked.")])
    data = build_report(spec)
    assert data["criteria"][0]["verdict"] == "UNPROVEN"
    assert "not tested" in data["criteria"][0]["why"]
    text = render_report(data)
    assert "### ac:9 — UNPROVEN" in text
    assert any("`ac:9` is UNPROVEN" in warning for warning in data["warnings"])


def test_a_criterion_a_scenario_claims_but_never_asserts_is_unproven(tmp_path: Path) -> None:
    log = [_start(), _scenario_start("s", "ac:1"), _assert("s", 1, "looked at nothing in particular"), _scenario_stop("s"), _stop()]
    spec = _spec(tmp_path, log=log, criteria=[_criterion("ac:1", "Sign in works.")])
    row = build_report(spec)["criteria"][0]
    assert row["verdict"] == "UNPROVEN"
    assert "no assertion declares `covers`" in row["why"]


def test_an_aborted_scenario_proves_nothing_for_what_it_covered(tmp_path: Path) -> None:
    log = [
        _start(),
        _scenario_start("s", "ac:1"),
        _assert("s", 1, "the part before the crash", "ac:1"),
        _scenario_stop("s", "failed", aborted=True, message="Timeout 30000ms exceeded"),
        _stop("failed"),
    ]
    spec = _spec(tmp_path, log=log, criteria=[_criterion("ac:1", "Sign in works.")])
    data = build_report(spec)
    assert data["criteria"][0]["verdict"] == "UNPROVEN"
    assert "stopped early" in data["criteria"][0]["why"]
    assert any("`s` was aborted — Timeout 30000ms exceeded" in w for w in data["warnings"])
    assert "**aborted**" in render_report(data)


def test_a_sentinel_failure_does_not_fail_the_criterion(tmp_path: Path) -> None:
    log = [
        _start(),
        _scenario_start("s", "ac:1"),
        _assert("s", 1, "real check", "ac:1"),
        _assert("s", 2, "harness sentinel", "ac:1", result="FAIL", sentinel=True),
        _scenario_stop("s"),
        _stop(),
    ]
    spec = _spec(tmp_path, log=log, criteria=[_criterion("ac:1", "Sign in works.")])
    data = build_report(spec)
    assert data["criteria"][0]["verdict"] == "PASS"
    # The tally matches the runner's — sentinels included — and says how many are sentinels.
    assert data["counts"]["assertions"] == 2
    assert data["counts"]["failed"] == 1
    assert data["counts"]["sentinelsFailed"] == 1
    assert "1 of the failures are harness sentinels" in render_report(data)
    assert "harness sentinel" in render_report(data)


# ----------------------------------------------------------------------------- attribution


def test_assertions_and_screenshots_sit_under_the_step_that_recorded_them(tmp_path: Path) -> None:
    spec = _spec(tmp_path, log=_stamped_log(), criteria=[_criterion("ac:1", "Sign in works."), _criterion("ac:2", "Tree loads.")])
    data = build_report(spec)
    scenario = data["scenarios"][0]
    assert scenario["stamped"] is True
    assert [step["label"] for step in scenario["steps"]] == [STEP_ONE[1], STEP_TWO[1]]
    assert [view["id"] for view in scenario["steps"][0]["asserts"]] == ["s-1"]
    assert [view["path"] for view in scenario["steps"][0]["artifacts"]] == ["qa/screenshots/after-sign-in.png"]
    assert [view["id"] for view in scenario["steps"][1]["asserts"]] == ["s-2"]
    assert [view["id"] for view in scenario["outside"]["asserts"]] == ["s-3"]

    text = render_report(data)
    ac1 = text.split("### ac:1 — PASS", 1)[1].split("### ac:2", 1)[0]
    assert "_Step: sign in with the provisioned account_" in ac1
    assert "the tree has a root" not in ac1
    assert "![after-sign-in.png](qa/screenshots/after-sign-in.png)" in ac1
    assert "[s-1.json](qa/asserts/s-1.json)" in ac1
    # The step-by-step account lists every step once, in order, and the stray assertion apart.
    steps = text.split("## Scenarios, step by step", 1)[1]
    assert steps.index("1. **sign in with the provisioned account** — ok") < steps.index("2. **fetch the page tree** — ok")
    assert "- _Outside any step_" in steps
    assert "✓ tidy-up succeeded — actual `ok` (covers nothing)" in steps


def test_a_step_the_ledger_never_closed_is_marked_unfinished(tmp_path: Path) -> None:
    log = [
        _start(),
        _scenario_start("s", "ac:1"),
        _assert("s", 1, "first look", "ac:1", step=STEP_ONE),
        _step("s", *STEP_ONE, exit_code=1, unfinished=True),
        _scenario_stop("s", "failed", aborted=True),
        _stop("failed"),
    ]
    spec = _spec(tmp_path, log=log, criteria=[_criterion("ac:1", "Sign in works.")])
    data = build_report(spec)
    assert data["scenarios"][0]["steps"][0]["unfinished"] is True
    text = render_report(data)
    assert "— **did not finish**" in text
    assert "— did not finish" in text.split("## Scenarios, step by step", 1)[1]


def test_a_step_stamped_but_never_recorded_is_also_unfinished(tmp_path: Path) -> None:
    log = [_start(), _scenario_start("s", "ac:1"), _assert("s", 1, "first look", "ac:1", step=STEP_ONE), _scenario_stop("s", "failed", aborted=True), _stop("failed")]
    spec = _spec(tmp_path, log=log, criteria=[_criterion("ac:1", "Sign in works.")])
    step = build_report(spec)["scenarios"][0]["steps"][0]
    assert step["label"] == STEP_ONE[1]
    assert step["unfinished"] is True


def test_a_ledger_without_stamps_lists_assertions_per_scenario_and_says_so(tmp_path: Path) -> None:
    """Order cannot tell an assertion inside a step from one between two steps, so the
    report does not guess — and tells the reader why there is no step-by-step account."""
    log = [
        _start(),
        _scenario_start("s", "ac:1"),
        _assert("s", 1, "first look", "ac:1"),
        _step("s", *STEP_ONE),
        _assert("s", 2, "second look", "ac:1"),
        _scenario_stop("s"),
        _stop(),
    ]
    spec = _spec(tmp_path, log=log, criteria=[_criterion("ac:1", "Sign in works.")])
    data = build_report(spec)
    scenario = data["scenarios"][0]
    assert scenario["stamped"] is False
    assert scenario["steps"][0]["asserts"] == []
    assert [view["id"] for view in scenario["outside"]["asserts"]] == ["s-1", "s-2"]
    assert any("predates step stamps" in warning for warning in data["warnings"])
    assert "this ledger does not say which step each ran in" in render_report(data)


# ----------------------------------------------------------------------------- obligations


def test_an_obligation_s_status_is_the_evidence_map_s(tmp_path: Path) -> None:
    obligation = {
        "id": CONTRACT, "kind": "contract", "node": "publish",
        "source": "docs/features/orders/publish.md",
        "requirement": "a stale manifest write is refused", "evidenceRequired": "live", "reasons": [],
        "checksDeclared": [{"call": DECLARED, "name": "conflict_on_stale", "args": {}}],
    }
    log = [
        _start(),
        _scenario_start("s", CONTRACT),
        _assert("s", 1, "a stale write is refused", CONTRACT, declared=DECLARED),
        _scenario_stop("s"),
        _stop(),
    ]
    evidence = {"runId": "qa-run-1", "obligations": [{"id": CONTRACT, "verdict": "pass", "log_refs": ["s-1"], "evidence": []}]}
    spec = _spec(tmp_path, log=log, obligations=[obligation], evidence=evidence)
    data = build_report(spec)
    expected = build_evidence_map(spec)["obligations"][0]["status"]
    assert data["obligations"][0]["status"] == expected
    assert data["obligations"][0]["checksDeclared"] == [DECLARED]
    text = render_report(data)
    assert f"| `{CONTRACT}` |" in text
    assert "Declared checks: `" + DECLARED + "`" in text


def test_a_context_only_obligation_owes_nothing_and_is_not_a_row(tmp_path: Path) -> None:
    obligation = {"id": CONTRACT, "kind": "contract", "source": "x", "requirement": "r", "required": False, "evidenceRequired": "context"}
    spec = _spec(tmp_path, log=_stamped_log(), obligations=[obligation])
    data = build_report(spec)
    assert data["obligations"] == []
    assert data["contextOnly"] == 1
    assert "No OKF obligations in scope" in render_report(data)


# ----------------------------------------------------------------------------- warnings


def test_the_warnings_name_what_a_reviewer_should_distrust(tmp_path: Path) -> None:
    log = [
        _start(),
        _scenario_start("s", "ac:1", "ac:77"),
        _assert("s", 1, "covers nothing"),
        _assert("s", 2, "no actual", "ac:1", actual=None),
        _assert("s", 3, "covers a ghost", "ac:78"),
        {"kind": "runner_error", "status": "invalid", "message": "driver cleanup failed", "problems": ["web: boom"]},
        _scenario_stop("s"),
        _stop(),
    ]
    spec = _spec(tmp_path, log=log, criteria=[_criterion("ac:1", "Sign in works.")])
    warnings = "\n".join(build_report(spec)["warnings"])
    assert "1 assertion(s) declare no `covers`" in warnings and "`s-1`" in warnings
    assert "recorded no `actual` value" in warnings and "`s-2`" in warnings
    assert "`ac:77` is covered by `s`" in warnings
    assert "`ac:78` is covered by `s-3`" in warnings
    assert "runner error: driver cleanup failed: web: boom" in warnings


def test_a_clean_run_has_no_warnings(tmp_path: Path) -> None:
    log = [_start(), _scenario_start("s", "ac:1"), _assert("s", 1, "looked", "ac:1", step=STEP_ONE), _step("s", *STEP_ONE), _scenario_stop("s"), _stop()]
    spec = _spec(tmp_path, log=log, criteria=[_criterion("ac:1", "Sign in works.")])
    data = build_report(spec)
    assert data["warnings"] == []
    assert "_None — every criterion" in render_report(data)


def test_a_run_that_never_closed_is_reported_incomplete(tmp_path: Path) -> None:
    log = [_start(), _scenario_start("s", "ac:1"), _assert("s", 1, "looked", "ac:1")]
    spec = _spec(tmp_path, log=log, criteria=[_criterion("ac:1", "Sign in works.")])
    data = build_report(spec)
    assert data["status"] == "incomplete"
    assert any("no session_stop" in w for w in data["warnings"])
    assert any("`s` never stopped" in w for w in data["warnings"])
    assert "**INCOMPLETE**" in render_report(data)


def test_a_missing_context_packet_is_a_warning_not_a_refusal(tmp_path: Path) -> None:
    spec = _spec(tmp_path, log=_stamped_log(), context=False)
    data = build_report(spec)
    assert data["criteria"] == []
    assert any("qa-okf-context.json is missing" in w for w in data["warnings"])


def test_a_missing_ledger_is_a_refusal(tmp_path: Path) -> None:
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    with pytest.raises(ReportError):
        build_report(spec)


# ----------------------------------------------------------------------------- writing


def test_the_scored_report_is_a_typed_spec_doc_carrying_its_run_id(tmp_path: Path) -> None:
    spec = _spec(tmp_path, log=_stamped_log(), criteria=[_criterion("ac:1", "Sign in works.")])
    path = write_report(spec)
    assert path == spec / REPORT_FILE == report_path(spec)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\ntype: spec.qa-report\n---\n")
    assert "<!-- run: qa-run-1 status: passed -->" in text
    assert run_id_of(path) == "qa-run-1"
    assert run_id_of(spec / "qa-okf-context.json") is None
    assert run_id_of(spec / "nope.md") is None


def test_a_dry_run_s_report_sits_beside_its_own_ledger_untyped(tmp_path: Path) -> None:
    spec = _spec(tmp_path, log=_stamped_log(), criteria=[_criterion("ac:1", "Sign in works.")], qa_dirname="qa/try-1")
    path = write_report(spec, label="try-1")
    assert path == spec / "qa/try-1/report.md"
    text = path.read_text(encoding="utf-8")
    assert not text.startswith("---")
    assert "(dry run `try-1`)" in text
    assert "`qa/try-1/qa-run.ndjson`" in text
    assert not (spec / REPORT_FILE).exists()
    assert write_report(spec, qa_dirname="qa/try-1") == path
    with pytest.raises(ValueError):
        write_report(spec, label="try-2", qa_dirname="qa/try-1")


def test_a_screenshot_s_vet_verdict_is_read_off_its_sidecar(tmp_path: Path) -> None:
    spec = _spec(tmp_path, log=_stamped_log(), criteria=[_criterion("ac:1", "Sign in works.")])
    (spec / "qa/screenshots").mkdir(parents=True)
    (spec / "qa/screenshots/after-sign-in.vet.json").write_text(
        json.dumps({
            "schema": "vet-placement/1", "screen": "docs/features/web/gui/screens/tree.md", "state": "",
            "screenshot": "qa/screenshots/after-sign-in.png", "regionCount": 4,
            "verdicts": [
                {"node_id": "tree-root", "status": "matched", "detail": [], "bbox": None},
                {"node_id": "sign-out", "status": "missing", "detail": ["not found"], "bbox": None},
            ],
        }),
        encoding="utf-8",
    )
    text = render_report(build_report(spec), spec_dir=spec)
    assert "vet: screen `docs/features/web/gui/screens/tree.md`, 1 finding(s): sign-out missing" in text
    # Without a spec dir the screenshot is still linked; the verdict line is simply absent.
    assert "vet:" not in render_report(build_report(spec))


def test_rendering_is_deterministic(tmp_path: Path) -> None:
    spec = _spec(tmp_path, log=_stamped_log(), criteria=[_criterion("ac:1", "Sign in works.")])
    assert write_report(spec).read_text() == write_report(spec).read_text()


# ----------------------------------------------------------------------------- recordings


def test_a_stamped_step_is_placed_in_the_recording_of_its_target(tmp_path: Path) -> None:
    spec = _spec(tmp_path, log=_recorded_log(), criteria=[_criterion("ac:1", "Tree loads.")])
    data = build_report(spec)
    steps = data["scenarios"][0]["steps"]
    # (started − actionStart)/1000: the step's own clock minus the recording's first frame.
    assert steps[0]["video"] == {"path": "qa/videos/web.mp4", "at": 2.4, "until": 4.9}
    assert steps[1]["video"] == {"path": "qa/videos/web.mp4", "at": 4.9, "until": 5.25}
    assert data["recordings"][0]["actionStartOffsetMs"] == 8000

    text = render_report(data, spec_dir=spec)
    # The reader sees the player's clock, a seekable link, and the command that pulls the frames.
    assert "1. **sign in with the provisioned account** — ok — recording [0:02.4–0:04.9](qa/videos/web.mp4#t=2.4)" in text
    assert "`ostler qa frames --spec " in text
    assert "--step s-step-1`" in text
    ac1 = text.split("### ac:1 — PASS", 1)[1]
    assert "_Step: fetch the page tree_ — recording [0:04.9–0:05.2](qa/videos/web.mp4#t=4.9)" in ac1
    assert "| Frames |" in text


def test_a_step_is_not_placed_in_a_recording_it_is_outside_of(tmp_path: Path) -> None:
    log = _recorded_log()
    # Before the first frame entirely, and after the last one entirely.
    log[2]["started_offset_ms"], log[2]["ended_offset_ms"] = 1_000, 2_000
    log[4]["started_offset_ms"], log[4]["ended_offset_ms"] = 40_000, 41_000
    data = build_report(_spec(tmp_path, log=log))
    assert [step["video"] for step in data["scenarios"][0]["steps"]] == [None, None]
    assert " — recording " not in render_report(data)


def test_a_step_straddling_the_first_frame_is_clamped_to_it(tmp_path: Path) -> None:
    log = _recorded_log()
    log[2]["started_offset_ms"], log[2]["ended_offset_ms"] = 7_000, 9_000
    data = build_report(_spec(tmp_path, log=log))
    assert data["scenarios"][0]["steps"][0]["video"] == {"path": "qa/videos/web.mp4", "at": 0.0, "until": 1.0}


def test_an_unstamped_step_or_an_unrecorded_target_has_no_place(tmp_path: Path) -> None:
    # Older ledgers carry no step timestamps; an api scenario has no recording to sit in.
    log = [*_stamped_log()[:-1], _video(), _stop()]
    data = build_report(_spec(tmp_path, log=log))
    assert all(step["video"] is None for step in data["scenarios"][0]["steps"])
    assert "| Frames |" in render_report(data)  # the recording exists, the hint still shows
    data = build_report(_spec(tmp_path, log=_stamped_log()))
    assert "| Frames |" not in render_report(data)
