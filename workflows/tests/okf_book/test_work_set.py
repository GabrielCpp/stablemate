"""The work set is written once, and a merge pass keeps only what the book has not stamped."""
from __future__ import annotations

from pathlib import Path

from ostler.stamp import digest_file

from workhorse_workflows.okf_book.citations import Citation, citations_in
from workhorse_workflows.okf_book.work_set import WorkSet, cited_digests, freeze, read_work_set, unstamped_files


def test_a_second_freeze_returns_the_first_work_set(tmp_path: Path) -> None:
    first = WorkSet(services=("tally",), files=("tally/cli.py",))
    assert read_work_set(tmp_path) is None
    assert freeze(tmp_path, first) == first
    assert freeze(tmp_path, WorkSet(services=("tally",), files=("late.py",))) == first
    assert read_work_set(tmp_path) == first


def test_a_merge_pass_keeps_new_unstamped_and_edited_files(tmp_path: Path) -> None:
    for name in ("same.py", "edited.py", "unstamped.py", "new.py"):
        _ = (tmp_path / name).write_text(f"{name}\n", encoding="utf-8")
    stamp = digest_file(b"same.py\n")
    cited = cited_digests([
        Citation("same.py", stamp),
        Citation("edited.py", digest_file(b"before\n")),
        Citation("unstamped.py", None),
    ])
    files = ["same.py", "edited.py", "unstamped.py", "new.py"]
    assert unstamped_files(tmp_path, files, cited) == {"edited.py", "unstamped.py", "new.py"}


def test_a_citation_reads_its_path_and_digest_and_skips_other_repos() -> None:
    text = "- code: `a/b.py::f` @0123456789ab\n- code: `repo://api-service/c.go::g`\n- code: d.py@ba9876543210\n"
    assert citations_in(text) == (
        Citation("a/b.py", "0123456789ab"),
        Citation("d.py", "ba9876543210"),
    )
