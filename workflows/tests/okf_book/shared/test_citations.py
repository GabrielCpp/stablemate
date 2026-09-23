"""A citation names a file of this repo and, once stamped, the digest the page was written against."""
from __future__ import annotations

from workhorse_workflows.okf_book.shared.citations import Citation, citations_in


def test_a_citation_reads_its_path_and_digest_and_skips_other_repos() -> None:
    text = "- code: `a/b.py::f` @0123456789ab\n- code: `repo://api-service/c.go::g`\n- code: d.py@ba9876543210\n"
    assert citations_in(text) == (
        Citation("a/b.py", "0123456789ab"),
        Citation("d.py", "ba9876543210"),
    )
