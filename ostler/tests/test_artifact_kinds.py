from __future__ import annotations

import json
import hashlib
from pathlib import Path

from ostler.artifact import get_kind, list_kinds, scaffold, vet
from ostler.artifact.kinds import (
    _backlog_items_vet,
    _plan_context_vet,
    _qa_evidence_vet,
)


def _spec(tmp_path: Path) -> Path:
    spec = tmp_path / "docs" / "specs" / "story-x"
    (spec / "qa").mkdir(parents=True)
    return spec


# ---------------------------------------------------------------------------
# plan-context
# ---------------------------------------------------------------------------

def test_plan_context_missing_services_is_actionable(tmp_path: Path):
    spec = _spec(tmp_path)
    problems = _plan_context_vet({"story": "x", "touched_layers": ["go"]}, spec, tmp_path)
    assert len(problems) == 1
    assert "touched_layers" in problems[0]
    assert "services" in problems[0]


def test_plan_context_valid_passes(tmp_path: Path):
    spec = _spec(tmp_path)
    (spec / "plan.md").write_text("# plan", encoding="utf-8")
    data = {
        "services": [{"repo": "acme", "path": "api", "type": "go", "plan_file": "plan.md"}],
        "implementation_order": ["acme::api"],
    }
    assert _plan_context_vet(data, spec, tmp_path) == []


def test_plan_context_flags_missing_plan_file_and_bad_order(tmp_path: Path):
    spec = _spec(tmp_path)
    data = {
        "services": [{"repo": "acme", "path": "api", "type": "go", "plan_file": "plan-go.md"}],
        "implementation_order": ["acme::web", "not-a-ref"],
    }
    problems = _plan_context_vet(data, spec, tmp_path)
    assert any("plan-go.md" in p for p in problems)
    assert any("acme::web" in p for p in problems)
    assert any("not-a-ref" in p for p in problems)


# ---------------------------------------------------------------------------
# qa-evidence
# ---------------------------------------------------------------------------

def _passing_evidence(spec: Path) -> dict:
    proof = spec / "qa" / "ac1.txt"
    proof.write_text("proof", encoding="utf-8")
    return {
        "overall": "Pass",
        "criteria": [
            {"id": "AC1", "kind": "behavioral", "verdict": "Pass",
             "evidence": [str(proof)]},
        ],
    }


def test_qa_evidence_missing_criteria_is_actionable(tmp_path: Path):
    spec = _spec(tmp_path)
    problems = _qa_evidence_vet({"result": "Pass", "acceptance_criteria": {}}, spec, tmp_path)
    assert len(problems) == 1
    assert "acceptance_criteria" in problems[0]
    assert "criteria" in problems[0]


def test_qa_evidence_valid_passes(tmp_path: Path):
    spec = _spec(tmp_path)
    data = _passing_evidence(spec)
    data.update({"runId": "qa-run-1", "qa_run_log": "qa/qa-run.ndjson"})
    data["criteria"][0]["log_refs"] = ["scenario-1:assert:1"]
    proof = spec / "qa" / "ac1.txt"
    (spec / "qa" / "qa-run.ndjson").write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {
                    "kind": "assert",
                    "scenario": "scenario-1",
                    "action": 1,
                    "result": "PASS",
                    "covers": ["AC1"],
                },
                {"kind": "session_stop", "run_id": "qa-run-1"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ledger = spec / "qa" / "qa-run.ndjson"
    (spec / "qa" / "run-manifest.json").write_text(
        json.dumps(
            {
                "runId": "qa-run-1",
                "artifacts": [
                    {
                        "path": "qa/ac1.txt",
                        "sha256": hashlib.sha256(proof.read_bytes()).hexdigest(),
                    },
                    {
                        "path": "qa/qa-run.ndjson",
                        "sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    assert _qa_evidence_vet(data, spec, tmp_path) == []


def test_qa_evidence_pass_without_real_evidence_fails(tmp_path: Path):
    spec = _spec(tmp_path)
    data = _passing_evidence(spec)
    data["criteria"][0]["evidence"] = ["qa/does-not-exist.png"]
    problems = _qa_evidence_vet(data, spec, tmp_path)
    assert any("no evidence file that exists" in p for p in problems)


def test_qa_evidence_overall_pass_with_fail_criterion_is_inconsistent(tmp_path: Path):
    spec = _spec(tmp_path)
    data = _passing_evidence(spec)
    data["criteria"].append({"id": "AC2", "kind": "behavioral", "verdict": "Fail"})
    problems = _qa_evidence_vet(data, spec, tmp_path)
    assert any("inconsistent" in p for p in problems)


def test_qa_evidence_parity_requires_checklist(tmp_path: Path):
    spec = _spec(tmp_path)
    data = _passing_evidence(spec)
    data["criteria"][0]["kind"] = "parity"
    problems = _qa_evidence_vet(data, spec, tmp_path)
    assert any("checklist" in p for p in problems)


def test_qa_evidence_divergent_checklist_row_fails(tmp_path: Path):
    spec = _spec(tmp_path)
    data = _passing_evidence(spec)
    proof = data["criteria"][0]["evidence"][0]
    data["criteria"][0]["kind"] = "parity"
    data["criteria"][0]["checklist"] = [
        {"element": "navbar", "verdict": "divergent", "evidence": proof},
    ]
    problems = _qa_evidence_vet(data, spec, tmp_path)
    assert any("divergent" in p for p in problems)


def test_qa_evidence_runid_requires_manifest(tmp_path: Path):
    spec = _spec(tmp_path)
    data = _passing_evidence(spec)
    data["runId"] = "qa-run-1"
    problems = _qa_evidence_vet(data, spec, tmp_path)
    assert any("run-manifest.json is missing" in p for p in problems)


def test_qa_evidence_runid_manifest_coherence(tmp_path: Path):
    spec = _spec(tmp_path)
    data = _passing_evidence(spec)
    data["runId"] = "qa-run-1"
    data["qa_run_log"] = "qa/qa-run.ndjson"
    data["criteria"][0]["log_refs"] = ["scenario-1:assert:1"]
    manifest = spec / "qa" / "run-manifest.json"
    proof = spec / "qa" / "ac1.txt"
    (spec / "qa" / "qa-run.ndjson").write_text(
        json.dumps(
            {
                "kind": "assert",
                "scenario": "scenario-1",
                "action": 1,
                "result": "PASS",
                "covers": ["AC1"],
            }
        )
        + "\n"
        + json.dumps({"kind": "session_stop", "run_id": "qa-run-1"})
        + "\n",
        encoding="utf-8",
    )
    ledger = spec / "qa" / "qa-run.ndjson"

    manifest.write_text(
        json.dumps(
            {
                "runId": "qa-run-1",
                "artifacts": [
                        {
                            "path": "qa/ac1.txt",
                            "sha256": hashlib.sha256(proof.read_bytes()).hexdigest(),
                        },
                        {
                            "path": "qa/qa-run.ndjson",
                            "sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
                        },
                ],
            }
        )
    )
    assert _qa_evidence_vet(data, spec, tmp_path) == []

    manifest.write_text(json.dumps({"runId": "qa-run-STALE", "artifacts": []}))
    problems = _qa_evidence_vet(data, spec, tmp_path)
    assert any("does not match" in p for p in problems)

    manifest.write_text(json.dumps({"runId": "qa-run-1", "artifacts": []}))
    problems = _qa_evidence_vet(data, spec, tmp_path)
    assert any("exact path" in p for p in problems)


# ---------------------------------------------------------------------------
# backlog-items
# ---------------------------------------------------------------------------

def test_backlog_items_rules(tmp_path: Path):
    spec = _spec(tmp_path)
    assert _backlog_items_vet([], spec, tmp_path) == []
    assert _backlog_items_vet({"not": "a list"}, spec, tmp_path)
    problems = _backlog_items_vet(
        [{"id": "ok-item", "description": "fine"},
         {"id": "Bad_Case", "description": "x"},
         {"id": "ok-item", "description": "dup"},
         {"id": "no-desc"}],
        spec, tmp_path,
    )
    assert any("kebab-case" in p for p in problems)
    assert any("duplicate" in p for p in problems)
    assert any("description" in p for p in problems)


# ---------------------------------------------------------------------------
# run orchestration
# ---------------------------------------------------------------------------

def test_scaffold_then_vet_roundtrip(tmp_path: Path):
    outcome = scaffold("backlog-items", Path("docs/specs/story-x"), tmp_path)
    assert outcome.status == "clean"
    outcome = vet("backlog-items", Path("docs/specs/story-x"), tmp_path)
    assert outcome.status == "clean"


def test_scaffold_refuses_overwrite_without_force(tmp_path: Path):
    spec = Path("docs/specs/story-x")
    assert scaffold("backlog-items", spec, tmp_path).status == "clean"
    assert scaffold("backlog-items", spec, tmp_path).status == "error"
    assert scaffold("backlog-items", spec, tmp_path, force=True).status == "clean"


def test_scaffolded_plan_context_fails_vet_until_filled(tmp_path: Path):
    # A fresh skeleton is deliberately NOT clean: placeholders must be replaced
    # and the plan file must exist before vet passes.
    spec = Path("docs/specs/story-x")
    assert scaffold("plan-context", spec, tmp_path).status == "clean"
    outcome = vet("plan-context", spec, tmp_path)
    assert outcome.status == "problems"


def test_unknown_kind_is_error(tmp_path: Path):
    assert scaffold("nope", Path("x"), tmp_path).status == "error"
    assert vet("nope", Path("x"), tmp_path).status == "error"
    assert get_kind("nope") is None
    assert {k["kind"] for k in list_kinds()} == {"plan-context", "qa-evidence", "backlog-items"}
