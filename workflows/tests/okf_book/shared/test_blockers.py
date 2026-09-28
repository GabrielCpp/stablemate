from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.shared.blockers import BLOCKERS_DIR, Blocker, Phase, Side, forget_blockers, read_blockers, record_blocker


def _book_blocker(service: str, problem: str) -> Blocker:
    return Blocker(subject=f"{service}: {problem}", service=service, phase=Phase.WRITE, side=Side.BOOK, reason=problem)


def test_forgetting_a_service_clears_its_book_blockers_and_keeps_every_other(tmp_path: Path) -> None:
    _ = record_blocker(tmp_path, _book_blocker("api", "page.md has no source"))
    kept_elsewhere = record_blocker(tmp_path, _book_blocker("api-docs", "page.md has no source"))
    kept_other_side = record_blocker(tmp_path, Blocker(subject="api", service="api", phase=Phase.WRITE, side=Side.WORKFLOW, reason="turn ended"))

    forget_blockers(tmp_path, Phase.WRITE, Side.BOOK, "api")

    assert read_blockers(tmp_path) == tuple(sorted((kept_elsewhere, kept_other_side), key=lambda blocker: blocker.subject))


def test_a_record_written_before_blockers_named_their_service_still_reads(tmp_path: Path) -> None:
    folder = tmp_path / BLOCKERS_DIR
    folder.mkdir()
    _ = (folder / "earlier.json").write_text('{"subject": "api: x", "phase": "write", "side": "book", "reason": "x"}', encoding="utf-8")

    assert [blocker.service for blocker in read_blockers(tmp_path)] == [""]
