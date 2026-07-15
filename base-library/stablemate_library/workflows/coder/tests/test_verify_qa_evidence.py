"""Unit tests for the deterministic QA evidence gate (scripts/verify_qa_evidence.py).

The gate can only invalidate a runner pass; it never upgrades. It fails closed when the
machine-checkable proof in <spec_dir>/qa-evidence.json is missing, malformed, references absent
evidence files, or is internally inconsistent (a parity criterion with a divergent element, a
data-entry criterion whose value did not persist, an overall Pass with a failing criterion).

Run with the system python3 (stdlib only), like the script itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "verify_qa_evidence.py"


def run_gate(sandbox: Path, spec_rel: str, status: str, notes: str = "") -> dict:
    """Invoke the gate as the workflow does and return the parsed qa_result."""
    env = dict(os.environ, AGENT_REPO_DIR=str(sandbox))
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), spec_rel, status, notes],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, f"gate crashed: {proc.stderr}"
    return json.loads(proc.stdout)["qa_result"]


def write_evidence(
    sandbox: Path, slug: str, evidence: dict, *, proof: bool = True
) -> Path:
    spec = sandbox / "docs" / "specs" / slug
    spec.mkdir(parents=True, exist_ok=True)
    qa = spec / "qa"
    qa.mkdir(exist_ok=True)
    (spec / "qa-plan.yml").write_text("version: 2\n", encoding="utf-8")
    (spec / "qa-okf-context.json").write_text(
        json.dumps({"version": 1, "available": True, "obligations": []}),
        encoding="utf-8",
    )
    if proof:
        (spec / "qa-proof.txt").write_text("ok\n", encoding="utf-8")
    evidence = {
        **evidence,
        "runId": "test-run",
        "qa_run_log": "qa/qa-run.ndjson",
    }
    records = []
    items = [*(evidence.get("criteria") or []), *(evidence.get("obligations") or [])]
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or item.get("verdict") != "Pass":
            continue
        scenario = f"scenario-{index}"
        item["log_refs"] = [f"{scenario}:assert:{index}"]
        records.append(
            {
                "kind": "assert",
                "scenario": scenario,
                "action": index,
                "result": "PASS",
                "covers": [item["id"]],
            }
        )
    records.append({"kind": "session_stop", "run_id": "test-run"})
    (qa / "qa-run.ndjson").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    ledger = qa / "qa-run.ndjson"
    artifacts = []
    proof_path = spec / "qa-proof.txt"
    if proof_path.is_file():
        artifacts.append(
            {
                "path": "qa-proof.txt",
                "sha256": hashlib.sha256(proof_path.read_bytes()).hexdigest(),
            }
        )
    artifacts.append(
        {
            "path": "qa/qa-run.ndjson",
            "sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
        }
    )
    (qa / "run-manifest.json").write_text(
        json.dumps({"runId": "test-run", "artifacts": artifacts}),
        encoding="utf-8",
    )
    (spec / "qa-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    return spec


def behavioral_pass() -> dict:
    return {
        "overall": "Pass",
        "criteria": [
            {
                "id": "AC1",
                "kind": "behavioral",
                "verdict": "Pass",
                "evidence": ["qa-proof.txt"],
            }
        ],
    }


def test_passthrough_when_not_claimed_pass(tmp_path):
    # A claimed fail/blocked is never touched by the gate (no evidence needed).
    assert run_gate(tmp_path, "docs/specs/s-1", "failed", "x")["status"] == "failed"
    assert run_gate(tmp_path, "docs/specs/s-1", "blocked", "y")["status"] == "blocked"


def test_valid_evidence_passes(tmp_path):
    write_evidence(tmp_path, "s-1", behavioral_pass())
    assert run_gate(tmp_path, "docs/specs/s-1", "passed")["status"] == "passed"


def test_missing_required_okf_obligation_is_invalid(tmp_path):
    spec = write_evidence(tmp_path, "s-1", behavioral_pass())
    (spec / "qa-okf-context.json").write_text(
        json.dumps(
            {
                "version": 1,
                "available": True,
                "obligations": [{"id": "okf:item:persists"}],
            }
        ),
        encoding="utf-8",
    )

    result = run_gate(tmp_path, "docs/specs/s-1", "passed")

    assert result["status"] == "invalid"
    assert "okf:item:persists" in result["notes"]


def test_missing_evidence_file_downgrades(tmp_path):
    (tmp_path / "docs" / "specs" / "s-1").mkdir(parents=True)
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"
    assert "missing" in res["notes"].lower()


def test_evidence_referencing_absent_file_downgrades(tmp_path):
    write_evidence(
        tmp_path, "s-1", behavioral_pass(), proof=False
    )  # json present, proof file not
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"
    assert "evidence file" in res["notes"].lower()


def test_parity_without_checklist_downgrades(tmp_path):
    ev = {
        "overall": "Pass",
        "criteria": [
            {
                "id": "AC1",
                "kind": "parity",
                "verdict": "Pass",
                "evidence": ["qa-proof.txt"],
            }
        ],
    }
    write_evidence(tmp_path, "s-1", ev)
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"
    assert "checklist" in res["notes"].lower()


def test_parity_divergent_row_downgrades(tmp_path):
    ev = {
        "overall": "Pass",
        "criteria": [
            {
                "id": "AC1",
                "kind": "parity",
                "verdict": "Pass",
                "evidence": ["qa-proof.txt"],
                "checklist": [
                    {
                        "element": "navbar ACCESS",
                        "verdict": "divergent",
                        "evidence": "qa-proof.txt",
                    }
                ],
            }
        ],
    }
    write_evidence(tmp_path, "s-1", ev)
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"
    assert "divergent" in res["notes"].lower()


def test_parity_all_match_passes(tmp_path):
    ev = {
        "overall": "Pass",
        "criteria": [
            {
                "id": "AC1",
                "kind": "parity",
                "verdict": "Pass",
                "evidence": ["qa-proof.txt"],
                "checklist": [
                    {
                        "element": "navbar ACCESS",
                        "verdict": "match",
                        "evidence": "qa-proof.txt",
                    },
                    {
                        "element": "✔ checkmark",
                        "verdict": "match",
                        "evidence": "qa-proof.txt",
                    },
                ],
            }
        ],
    }
    write_evidence(tmp_path, "s-1", ev)
    assert run_gate(tmp_path, "docs/specs/s-1", "passed")["status"] == "passed"


def test_data_entry_not_persisted_downgrades(tmp_path):
    ev = {
        "overall": "Pass",
        "criteria": [
            {
                "id": "AC1",
                "kind": "data-entry",
                "verdict": "Pass",
                "evidence": ["qa-proof.txt"],
                "persistence": {
                    "persisted": False,
                    "bled_to_others": False,
                    "evidence": "qa-proof.txt",
                },
            }
        ],
    }
    write_evidence(tmp_path, "s-1", ev)
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"
    assert "persist" in res["notes"].lower()


def test_data_entry_bleed_downgrades(tmp_path):
    ev = {
        "overall": "Pass",
        "criteria": [
            {
                "id": "AC1",
                "kind": "data-entry",
                "verdict": "Pass",
                "evidence": ["qa-proof.txt"],
                "persistence": {
                    "persisted": True,
                    "bled_to_others": True,
                    "evidence": "qa-proof.txt",
                },
            }
        ],
    }
    write_evidence(tmp_path, "s-1", ev)
    assert run_gate(tmp_path, "docs/specs/s-1", "passed")["status"] == "invalid"


def test_data_entry_persisted_passes(tmp_path):
    ev = {
        "overall": "Pass",
        "criteria": [
            {
                "id": "AC1",
                "kind": "data-entry",
                "verdict": "Pass",
                "evidence": ["qa-proof.txt"],
                "persistence": {
                    "persisted": True,
                    "bled_to_others": False,
                    "evidence": "qa-proof.txt",
                },
            }
        ],
    }
    write_evidence(tmp_path, "s-1", ev)
    assert run_gate(tmp_path, "docs/specs/s-1", "passed")["status"] == "passed"


def test_failing_criterion_blocks_overall_pass(tmp_path):
    ev = {
        "overall": "Pass",
        "criteria": [
            {
                "id": "AC1",
                "kind": "behavioral",
                "verdict": "Pass",
                "evidence": ["qa-proof.txt"],
            },
            {
                "id": "AC2",
                "kind": "behavioral",
                "verdict": "Fail",
                "evidence": ["qa-proof.txt"],
            },
        ],
    }
    write_evidence(tmp_path, "s-1", ev)
    assert run_gate(tmp_path, "docs/specs/s-1", "passed")["status"] == "invalid"


def _transient_criterion(**over) -> dict:
    t = {
        "trigger": "clicked Save",
        "appeared": True,
        "disappeared": True,
        "mid_window_capture": "qa-proof.txt",
    }
    t.update(over.pop("transient", {}))
    c = {
        "id": "AC1",
        "kind": "transient",
        "verdict": "Pass",
        "evidence": ["qa-proof.txt"],
        "transient": t,
    }
    c.update(over)
    return {"overall": "Pass", "criteria": [c]}


def test_transient_appear_then_disappear_passes(tmp_path):
    write_evidence(tmp_path, "s-1", _transient_criterion())
    assert run_gate(tmp_path, "docs/specs/s-1", "passed")["status"] == "passed"


def test_transient_without_block_downgrades(tmp_path):
    ev = {
        "overall": "Pass",
        "criteria": [
            {
                "id": "AC1",
                "kind": "transient",
                "verdict": "Pass",
                "evidence": ["qa-proof.txt"],
            }
        ],
    }
    write_evidence(tmp_path, "s-1", ev)
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"
    assert "transient" in res["notes"].lower()


def test_transient_never_appeared_downgrades(tmp_path):
    write_evidence(tmp_path, "s-1", _transient_criterion(transient={"appeared": False}))
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"
    assert "appear" in res["notes"].lower()


def test_transient_never_disappeared_downgrades(tmp_path):
    write_evidence(
        tmp_path, "s-1", _transient_criterion(transient={"disappeared": False})
    )
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"
    assert "disappear" in res["notes"].lower()


def test_transient_without_mid_window_capture_downgrades(tmp_path):
    # cites a settled frame that exists, but no mid_window_capture → must downgrade
    write_evidence(
        tmp_path, "s-1", _transient_criterion(transient={"mid_window_capture": ""})
    )
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"
    assert (
        "mid_window_capture" in res["notes"].lower()
        or "mid-window" in res["notes"].lower()
    )


def test_transient_mid_window_capture_absent_file_downgrades(tmp_path):
    write_evidence(
        tmp_path,
        "s-1",
        _transient_criterion(transient={"mid_window_capture": "does-not-exist.png"}),
    )
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"


def test_malformed_json_downgrades(tmp_path):
    spec = tmp_path / "docs" / "specs" / "s-1"
    spec.mkdir(parents=True)
    (spec / "qa-evidence.json").write_text("{not json", encoding="utf-8")
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"
    assert "json" in res["notes"].lower()


def _write_vet_report(
    spec: Path, name: str, summary: dict, *, missing: list | None = None
) -> str:
    report = {
        "summary": {
            "matchedCount": 0,
            "missingCount": 0,
            "unexpectedCount": 0,
            "unlabeledCount": 0,
            **summary,
        },
        "missing": missing or [],
    }
    (spec / name).write_text(json.dumps(report), encoding="utf-8")
    return name


def test_visual_fidelity_missing_report_file_downgrades(tmp_path):
    ev = behavioral_pass()
    ev["visual_fidelity"] = [{"state": "default", "report": "vet/default-report.json"}]
    write_evidence(tmp_path, "s-1", ev)
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"
    assert "visual_fidelity" in res["notes"].lower()


def test_visual_fidelity_missing_count_downgrades_with_selectors(tmp_path):
    spec = write_evidence(tmp_path, "s-1", behavioral_pass())
    _write_vet_report(
        spec,
        "vet-report.json",
        {"missingCount": 1},
        missing=[{"selector": "button.export-cta", "role": "button"}],
    )
    ev = behavioral_pass()
    ev["visual_fidelity"] = [{"state": "default", "report": "vet-report.json"}]
    write_evidence(tmp_path, "s-1", ev)
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "invalid"
    assert "button.export-cta" in res["notes"]


def test_visual_fidelity_unexpected_and_unlabeled_do_not_downgrade(tmp_path):
    spec = write_evidence(tmp_path, "s-1", behavioral_pass())
    _write_vet_report(
        spec,
        "vet-report.json",
        {"matchedCount": 3, "unexpectedCount": 2, "unlabeledCount": 5},
    )
    ev = behavioral_pass()
    ev["visual_fidelity"] = [{"state": "default", "report": "vet-report.json"}]
    write_evidence(tmp_path, "s-1", ev)
    res = run_gate(tmp_path, "docs/specs/s-1", "passed")
    assert res["status"] == "passed"
    assert "informational only" in res["notes"]


def test_visual_fidelity_absent_claim_does_not_affect_pass(tmp_path):
    # No visual_fidelity claim at all — must not be treated as a downgrade condition.
    write_evidence(tmp_path, "s-1", behavioral_pass())
    assert run_gate(tmp_path, "docs/specs/s-1", "passed")["status"] == "passed"
