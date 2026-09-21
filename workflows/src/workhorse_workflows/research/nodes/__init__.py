"""The research workflow's non-agent work, grouped by subject."""
from __future__ import annotations

from workhorse_workflows.research.nodes._blueprint import blueprint
from workhorse_workflows.research.nodes.dossier import build_dossier
from workhorse_workflows.research.nodes.history import append_history
from workhorse_workflows.research.nodes.measure import (
    check_envelope,
    classify_fault,
    collect_job,
    dry_run,
    job_dir_for,
    kill_job,
    submit_job,
    watch_job,
)
from workhorse_workflows.research.nodes.program import load_program, record_spend
from workhorse_workflows.research.nodes.publish import publish_results
from workhorse_workflows.research.nodes.setup import clone_repo

__all__ = [
    "append_history",
    "blueprint",
    "build_dossier",
    "check_envelope",
    "classify_fault",
    "clone_repo",
    "collect_job",
    "dry_run",
    "job_dir_for",
    "kill_job",
    "load_program",
    "publish_results",
    "record_spend",
    "submit_job",
    "watch_job",
]
