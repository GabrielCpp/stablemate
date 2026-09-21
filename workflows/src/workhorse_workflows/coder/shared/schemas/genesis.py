"""Genesis's models: what the target already is, what each step made of it, and the verdict."""
from __future__ import annotations

from typing import Literal

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class TargetClassification(CoderResult):
    """`resolve-genesis-target.py` — what is already at the target, before anything runs."""

    ok: bool = False
    target_dir: str = ""
    target_state: Literal["absent", "partial", "existing"] = "absent"
    service_state: Literal["existing", "absent"] = "absent"
    service: str = ""
    markers: list[str] = []
    note: str = ""


class GitInit(CoderResult):
    """`genesis-git-init.py` — a repo with at least one commit, made or found."""

    ready: bool = False
    note: str = ""
    initial_commit: str = ""


class AgentsYml(CoderResult):
    """`write-genesis-agents-yml.py` — the config merged in, or found already correct."""

    written: bool = False
    path: str = ""
    note: str = ""


class Skeleton(CoderResult):
    """`init-genesis-skeleton.py` — the stack's own `init` command, and its proof."""

    ok: bool = False
    note: str = ""
    marker_path: str = ""


class FarrierInstall(CoderResult):
    """`install-genesis-farrier.py` — adapters rendered, and the scaffolds that took."""

    ok: bool = False
    note: str = ""
    scaffolds_rendered: list[str] = []


class GenesisReport(CoderResult):
    """`validate-genesis.py` — every precondition the main loop assumes, checked."""

    valid: bool = False
    errors: str = ""
    warnings: str = ""


__all__ = [
    "AgentsYml",
    "FarrierInstall",
    "GenesisReport",
    "GitInit",
    "Skeleton",
    "TargetClassification",
]
