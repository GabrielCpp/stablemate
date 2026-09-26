"""The subjects a book is committed under, which tell a rerun whether this workflow finished it."""
from __future__ import annotations


def book_commit_subject(service: str) -> str:
    """The subject of a book this workflow's writer finished."""
    return f"docs({service}): write the {service} book"


def unfinished_book_commit_subject(service: str) -> str:
    """The subject of the pages a failed writer turn left, so a rerun sends a writer to finish them."""
    return f"docs({service}): keep the unfinished {service} book"
