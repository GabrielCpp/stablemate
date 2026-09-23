"""A merge pass keeps only the files the book has not stamped at their current digest."""
from __future__ import annotations

from pathlib import Path

from ostler.stamp import digest_file

from workhorse_workflows.okf_book.main.nodes.unstamped import cited_digests, unstamped_files
from workhorse_workflows.okf_book.shared.citations import Citation


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
