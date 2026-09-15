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


def test_fingerprint_is_order_independent(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def bar(): pass\n", encoding="utf-8")
    refs = ["a.py::Foo", "b.py"]
    fixtures = {"fx-1": "setup text", "fx-2": "other text"}
    assert claim_fingerprint(refs, fixtures, "plan-1", tmp_path) == claim_fingerprint(
        list(reversed(refs)), fixtures, "plan-1", tmp_path
    )


def test_fingerprint_changes_when_a_cited_digest_changes() -> None:
    """A stamp is a copy, not the original — the fingerprint must not depend on it."""
    before = claim_fingerprint(["a.py@abc123abc123"], {}, "plan-1", Path("/nonexistent"))
    after = claim_fingerprint(["a.py@def456def456"], {}, "plan-1", Path("/nonexistent"))
    assert before == after


def test_fingerprint_changes_when_cited_file_bytes_change(tmp_path: Path) -> None:
    """The fingerprint must move when a cited file's real bytes change, stamp or no stamp.

    This is the core defect this fix closes: fingerprinting the book's `@digest` stamp text
    (a copy) instead of the cited file's actual bytes meant a code change with no matching
    restamp — or a re-run performed before doctor's stale-citation check ran — was invisible
    to the fingerprint, and a targeted re-run would wrongly skip a claim whose dependency had
    moved.
    """
    cited = tmp_path / "a.py"
    cited.write_text("def foo(): return 1\n", encoding="utf-8")

    before = claim_fingerprint(["a.py"], {}, "plan-1", tmp_path)
    cited.write_text("def foo(): return 2\n", encoding="utf-8")
    after = claim_fingerprint(["a.py"], {}, "plan-1", tmp_path)

    assert before != after


def test_fingerprint_sensitive_to_file_bytes_with_no_stamp_at_all(tmp_path: Path) -> None:
    """An unstamped citation (no `@digest` suffix) still fingerprints by the file's real bytes."""
    cited = tmp_path / "a.py"
    cited.write_text("def foo(): return 1\n", encoding="utf-8")

    before = claim_fingerprint(["a.py::foo"], {}, "plan-1", tmp_path)
    cited.write_text("def foo(): return 999\n", encoding="utf-8")
    after = claim_fingerprint(["a.py::foo"], {}, "plan-1", tmp_path)

    assert before != after


def test_needs_rerun_true_when_cited_file_changed_even_though_book_did_not(tmp_path: Path) -> None:
    """A targeted re-run must not skip a claim whose cited file drifted with no book change."""
    ledger_file = tmp_path / "acme.ledger.json"
    cited = tmp_path / "a.py"
    cited.write_text("def foo(): return 1\n", encoding="utf-8")

    fingerprint = claim_fingerprint(["a.py::foo"], {}, "plan-1", tmp_path)
    ledger = record_result(ledger_file, load_ledger(ledger_file), "okf:node#does:1", fingerprint, "checked")
    assert needs_rerun(ledger, "okf:node#does:1", fingerprint) is False

    # The file's real bytes change; nothing in the book (no stamp, no plan text) is touched.
    cited.write_text("def foo(): return 2\n", encoding="utf-8")
    moved_fingerprint = claim_fingerprint(["a.py::foo"], {}, "plan-1", tmp_path)

    assert needs_rerun(ledger, "okf:node#does:1", moved_fingerprint) is True


def test_fingerprint_changes_when_fixture_text_changes() -> None:
    before = claim_fingerprint([], {"fx-1": "setup text"}, "plan-1", Path("/nonexistent"))
    after = claim_fingerprint([], {"fx-1": "different setup"}, "plan-1", Path("/nonexistent"))
    assert before != after


def test_fingerprint_changes_when_claim_content_changes(tmp_path: Path) -> None:
    """A repaired expected value must invalidate the fingerprint even when nothing cited did."""
    (tmp_path / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
    before = claim_fingerprint(["a.py"], {"fx-1": "setup text"}, "expect: 200", tmp_path)
    after = claim_fingerprint(["a.py"], {"fx-1": "setup text"}, "expect: 204", tmp_path)
    assert before != after


def test_fingerprint_unreadable_cited_file_is_stable_not_a_crash(tmp_path: Path) -> None:
    """A citation that cannot be resolved (moved, wrong root) folds in a sentinel, not a raise."""
    fingerprint = claim_fingerprint(["missing.py"], {}, "plan-1", tmp_path)
    assert claim_fingerprint(["missing.py"], {}, "plan-1", tmp_path) == fingerprint


def test_repo_qualified_ref_does_not_silently_hash_the_local_file(tmp_path: Path) -> None:
    """A foreign-repository ref must not fall back onto the local checkout's own file.

    `a.py` exists locally at the same relative path a `repo://other/a.py` ref names. With no
    `checkouts` supplied, resolving the qualified ref against `repo_root` would silently
    fingerprint *that* unrelated local file instead of reporting the citation unreadable — a
    wrong-file fingerprint, not a missing-file one. It must instead fold into the same
    sentinel an unreadable citation always does, so it is indistinguishable from "cannot be
    read" rather than tracking content that has nothing to do with the citation.
    """
    local = tmp_path / "a.py"
    local.write_text("def foo(): return 'wrong file'\n", encoding="utf-8")

    qualified_with_local_file = claim_fingerprint(["repo://other/a.py"], {}, "plan-1", tmp_path)
    qualified_with_no_local_file = claim_fingerprint(
        ["repo://other/a.py"], {}, "plan-1", tmp_path / "nonexistent-root"
    )

    # Whether the local checkout happens to have a file at that same relative path makes no
    # difference: neither root resolves the foreign repository, so both fold into the same
    # unreadable sentinel rather than the one with a local file hashing it by accident.
    assert qualified_with_local_file == qualified_with_no_local_file
    # And it must not equal what fingerprinting the local file's real bytes would produce.
    local_hash = claim_fingerprint(["a.py"], {}, "plan-1", tmp_path)
    assert qualified_with_local_file != local_hash


def test_repo_qualified_ref_resolves_against_its_named_checkout(tmp_path: Path) -> None:
    """A `repo://` ref with a matching entry in `checkouts` resolves there, not against `repo_root`."""
    other_checkout = tmp_path / "other-checkout"
    other_checkout.mkdir()
    (other_checkout / "a.py").write_text("def foo(): return 'other repo'\n", encoding="utf-8")
    local = tmp_path / "a.py"
    local.write_text("def foo(): return 'local repo'\n", encoding="utf-8")

    resolved = claim_fingerprint(
        ["repo://other/a.py"], {}, "plan-1", tmp_path, checkouts={"other": other_checkout}
    )
    unreadable = claim_fingerprint(["missing-anywhere.py"], {}, "plan-1", tmp_path)
    local_hash = claim_fingerprint(["a.py"], {}, "plan-1", tmp_path)

    assert resolved != unreadable
    assert resolved != local_hash

    (other_checkout / "a.py").write_text("def foo(): return 'changed'\n", encoding="utf-8")
    changed = claim_fingerprint(
        ["repo://other/a.py"], {}, "plan-1", tmp_path, checkouts={"other": other_checkout}
    )
    assert changed != resolved


def test_repo_qualified_ref_naming_the_books_own_repository_is_local(tmp_path: Path) -> None:
    """A ref qualified with the book's own repository resolves against `repo_root`, like a bare one."""
    local = tmp_path / "a.py"
    local.write_text("def foo(): return 1\n", encoding="utf-8")

    bare = claim_fingerprint(["a.py"], {}, "plan-1", tmp_path, own_repository="acme")
    own_qualified = claim_fingerprint(
        ["repo://acme/a.py"], {}, "plan-1", tmp_path, own_repository="acme"
    )
    assert bare == own_qualified


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
