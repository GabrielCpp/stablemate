"""What the parity surveyor validates. Its node returns, and nothing else.

The parity survey answers one question — which legacy surfaces have no home in the new
app — so it reuses the surveyor's whole per-unit machinery (`select_next_unit`,
`validate_record`, `mark_unit`, `verify_records`) and differs only at the ends: how the
frozen list is built, and what gets emitted from it. Those ends are here.

`Expansion` and `EmitResult` are deliberately NOT re-declared: the parity scripts emit the
same four keys under the same names, so the two flows share one shape and only the node
that fills it differs.
"""
from __future__ import annotations

from workhorse_workflows.author.schemas._base import AuthorResult

# ── node returns ────────────────────────────────────────────────────────────


class ParityConfig(AuthorResult):
    """`load_parity_config` — the two documentation inventories being compared.

    A separate model from `SurveyConfig` rather than a superset of it, because the parity
    survey has no rubric, no enumeration rules, no partition and no context file: its
    units come from a baseline inventory that already exists, and its emission needs no
    clustering step. Modelling that as one config with half its fields blank would make
    every reader ask which half applied.

    Every path but `repo_root` is repo-relative, exactly as the script emitted it.
    """

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
