"""The subjects a book is committed under, which tell a rerun whether this workflow finished it."""
from __future__ import annotations


def book_commit_subject(service: str) -> str:
    """The subject of a book this workflow's writer finished."""
    return f"docs({service}): write the {service} book"


def unfinished_book_commit_subject(service: str) -> str:
    """The subject of the pages a failed writer turn left, so a rerun sends a writer to finish them."""
    return f"docs({service}): keep the unfinished {service} book"


def rooted_book_commit_subject(service: str) -> str:
    """The subject of the entries page code wrote for a book that had none."""
    return f"docs({service}): root the {service} book"


def repaired_book_commit_subject(service: str) -> str:
    """The subject of the pages one repair turn changed. A rerun checks and runs such a book as this workflow's own, and never repairs it again."""
    return f"docs({service}): repair pages of the {service} book"
