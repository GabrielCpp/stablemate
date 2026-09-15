"""The result ledger: fingerprint stability and the persisted record round trip.

`claim_fingerprint` is the one piece of actual logic here — everything else is JSON state
management, the same shape `shared/worklist.py`'s `record`/`load_worklist` already have
tests for indirectly. What is under test is the property the plan's slice depends on: a
targeted re-run skips a claim exactly when nothing it depends on changed, and re-runs it
the moment a cited file's stamped digest or a fixture's text does.
"""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared.ledger import (
    claim_fingerprint,
    load_ledger,
    needs_rerun,
    record_result,
)


def test_ledger_path_is_one_file_per_service(tmp_path: Path) -> None:
    assert paths.ledger_path(tmp_path, "acme") == tmp_path / ".agents" / "okf-build" / "acme.ledger.json"
    assert paths.ledger_path(tmp_path, "") == tmp_path / ".agents" / "okf-build" / "all.ledger.json"


def test_fingerprint_is_order_independent() -> None:
    refs = ["a.py::Foo@abc123", "b.py@def456"]
    fixtures = {"fx-1": "setup text", "fx-2": "other text"}
    assert claim_fingerprint(refs, fixtures, "plan-1") == claim_fingerprint(
        list(reversed(refs)), fixtures, "plan-1"
    )


def test_fingerprint_changes_when_a_cited_digest_changes() -> None:
    before = claim_fingerprint(["a.py@abc123"], {}, "plan-1")
    after = claim_fingerprint(["a.py@def456"], {}, "plan-1")
    assert before != after


def test_fingerprint_changes_when_fixture_text_changes() -> None:
    before = claim_fingerprint([], {"fx-1": "setup text"}, "plan-1")
    after = claim_fingerprint([], {"fx-1": "different setup"}, "plan-1")
    assert before != after


def test_fingerprint_changes_when_claim_content_changes() -> None:
    """A repaired expected value must invalidate the fingerprint even when nothing cited did."""
    before = claim_fingerprint(["a.py@abc123"], {"fx-1": "setup text"}, "expect: 200")
    after = claim_fingerprint(["a.py@abc123"], {"fx-1": "setup text"}, "expect: 204")
    assert before != after


def test_load_ledger_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_ledger(tmp_path / "nope.ledger.json") == {"claims": {}}


def test_load_ledger_corrupted_json_falls_back_to_empty(tmp_path: Path) -> None:
    path = tmp_path / "bad.ledger.json"
    path.write_text("not json", encoding="utf-8")
    assert load_ledger(path) == {"claims": {}}


def test_needs_rerun_with_no_record() -> None:
    assert needs_rerun({"claims": {}}, "okf:node#does:1", "fp-1") is True


def test_record_result_persists_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "acme.ledger.json"
    ledger = load_ledger(path)
    ledger = record_result(path, ledger, "okf:node#does:1", "fp-1", "checked", note="ok")

    reloaded = load_ledger(path)
    assert reloaded["claims"]["okf:node#does:1"] == {
        "fingerprint": "fp-1",
        "verdict": "checked",
        "note": "ok",
    }


def test_needs_rerun_tracks_fingerprint_change(tmp_path: Path) -> None:
    path = tmp_path / "acme.ledger.json"
    ledger = record_result(path, load_ledger(path), "okf:node#does:1", "fp-1", "checked")

    assert needs_rerun(ledger, "okf:node#does:1", "fp-1") is False
    assert needs_rerun(ledger, "okf:node#does:1", "fp-2") is True
