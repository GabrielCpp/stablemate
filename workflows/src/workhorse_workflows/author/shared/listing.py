"""The open debt register as the block of text a prompt reads."""
from __future__ import annotations

from pathlib import Path

from ostler import Ostler

LISTING_HEADER = "id\trepo\tarea\tstatus\tpattern\tsummary"
NO_OPEN_RECORDS = "no open records"


def open_listing(repo_dir: str | Path, repo: str = "") -> str:
    """One line per open record under a header, for *repo* or for every repository."""
    lines = Ostler(repo_dir).record_listing(repo=repo, status="open")
    return "\n".join([LISTING_HEADER, *lines]) if lines else NO_OPEN_RECORDS
