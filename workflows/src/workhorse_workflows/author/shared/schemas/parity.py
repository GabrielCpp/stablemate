"""What the parity surveyor validates."""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas._base import AuthorResult



class ParityConfig(AuthorResult):
    """`load_parity_config` — the baseline inventory and the books it is compared with."""

    repo_root: str = ""
    baseline_inventory: str = ""
    survey_dir: str = ""
    inventory: str = ""
    findings_dir: str = ""
    unit_manifest: str = ""
    epics_dir: str = ""


__all__ = ["ParityConfig"]
