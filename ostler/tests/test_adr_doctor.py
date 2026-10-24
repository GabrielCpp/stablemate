"""The doctor's two checks over decisions: evidence that resolves to nothing, and a back-link that points nowhere."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ostler import adr, doctor, register
from ostler._vendor.stablemate_core import config as core_config
from ostler.model import load


def artifacts() -> Path:
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve()


def decided(tmp_path: Path) -> str:
    core_config.ensure_artifacts_repo()
    graph = load(tmp_path)
    for record_id in ("acme-1", "acme-2", "acme-3"):
        filing = register.file_record(
            graph, repo="api-service", area="billing", pattern="guard-the-total",
            summary=f"summary of {record_id}", filed_by="qa", record_id=record_id,
        )
        assert filing.ok, filing.message
    result = adr.propose(
        load(tmp_path), title="Guard every total", context="c", decision="d", consequences="q",
        evidence=["acme-1", "acme-2", "acme-3"],
    )
    assert result.ok, result.message
    return result.entity_id


def findings(tmp_path: Path, code: str) -> list:
    return [f for f in doctor.run(load(tmp_path)).findings if f.code == code]


def test_an_intact_decision_yields_no_finding(tmp_path: Path) -> None:
    decided(tmp_path)

    assert not findings(tmp_path, "decision-evidence-unresolved")
    assert not findings(tmp_path, "decision-back-link-missing")


def test_evidence_whose_record_folder_was_deleted_is_named_with_its_decision(tmp_path: Path) -> None:
    decision_id = decided(tmp_path)
    shutil.rmtree(artifacts() / "backlog/api-service/billing/acme-2")

    found = findings(tmp_path, "decision-evidence-unresolved")

    assert len(found) == 1
    assert found[0].severity == "error"
    assert decision_id in found[0].message and "acme-2" in found[0].message


def test_a_record_naming_a_missing_decision_file_is_reported(tmp_path: Path) -> None:
    graph = load(tmp_path)
    core_config.ensure_artifacts_repo()
    filing = register.file_record(
        graph, repo="api-service", area="billing", pattern="guard-the-total",
        summary="summary", filed_by="qa", record_id="acme-9",
    )
    assert filing.path is not None
    filing.path.write_text(
        filing.path.read_text(encoding="utf-8").replace("decision: ''", "decision: acme-gone"),
        encoding="utf-8",
    )

    found = findings(tmp_path, "decision-back-link-missing")

    assert len(found) == 1
    assert found[0].severity == "error"
    assert "acme-9" in found[0].message and "acme-gone" in found[0].message


def test_a_decision_listing_a_record_bound_elsewhere_is_reported(tmp_path: Path) -> None:
    decision_id = decided(tmp_path)
    target = artifacts() / "backlog/api-service/billing/acme-3/record.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace(f"decision: {decision_id}", "decision: acme-other"),
        encoding="utf-8",
    )

    found = [f for f in findings(tmp_path, "decision-back-link-missing") if decision_id in f.message]

    assert len(found) == 1 and "acme-3" in found[0].message
