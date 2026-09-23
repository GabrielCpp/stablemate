"""Each kind of row is seeded once, so a resume walks the same rows in the same order."""
from __future__ import annotations

from pathlib import Path

from workhorse.worklist import WorkItem

from workhorse_workflows.okf_book.shared.work import DONE, FILE, ORPHAN, book_work, ids, seed


def _rows(kind: str, *names: str) -> list[WorkItem]:
    return [WorkItem(id=name, kind=kind, order=order) for order, name in enumerate(names)]


def test_a_kind_already_seeded_keeps_its_rows(tmp_path: Path) -> None:
    work = book_work(tmp_path)
    seed(work, FILE, _rows(FILE, "b.py", "a.py"))
    seed(work, FILE, _rows(FILE, "late.py"))

    assert ids(book_work(tmp_path), FILE) == ("b.py", "a.py")


def test_each_kind_is_seeded_on_its_own(tmp_path: Path) -> None:
    work = book_work(tmp_path)
    seed(work, FILE, _rows(FILE, "a.py"))
    seed(work, ORPHAN, _rows(ORPHAN, "gone.md"))

    assert (ids(work, FILE), ids(work, ORPHAN)) == (("a.py",), ("gone.md",))


def test_ids_at_a_status_keep_the_seeded_order(tmp_path: Path) -> None:
    work = book_work(tmp_path)
    seed(work, FILE, _rows(FILE, "c.py", "b.py", "a.py"))
    _ = work.mark("a.py", DONE, FILE)
    _ = work.mark("c.py", DONE, FILE)

    assert ids(work, FILE, DONE) == ("c.py", "a.py")


def test_a_kind_seeded_empty_stays_empty(tmp_path: Path) -> None:
    work = book_work(tmp_path)
    seed(work, ORPHAN, [])
    seed(work, ORPHAN, _rows(ORPHAN, "appeared-later.md"))

    assert ids(book_work(tmp_path), ORPHAN) == ()
