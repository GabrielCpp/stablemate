"""What the parity surveyor validates."""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas._base import AuthorResult



class ParityConfig(AuthorResult):
    """`load_parity_config` — the two documentation inventories being compared."""

    repo_root: str = ""
    baseline_inventory: str = ""
    target_features: str = ""
    survey_dir: str = ""
    inventory: str = ""
    findings_dir: str = ""
    unit_manifest: str = ""
    backlog: str = ""
    epics_dir: str = ""


__all__ = ["ParityConfig"]
