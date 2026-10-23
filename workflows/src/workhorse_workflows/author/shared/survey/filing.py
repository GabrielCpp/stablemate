"""Filing a survey's findings as records on the debt register, once per distinct finding."""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ostler import Ostler
from ostler.register import FiledBy
from workhorse_workflows.kit import commit_paths
from workhorse_workflows.kit.workspace import resolve_workspace

PATTERN = "untriaged"
_SEGMENT = re.compile(r"[^a-z0-9]+")
_SCOPE = re.compile(r"[^a-z0-9._-]+")


@dataclass(frozen=True)
class Proposal:
    """One finding to file: *key* names it to the caller, the rest becomes the record."""

    key: str
    area: str
    summary: str
    body: str = ""
    pattern: str = PATTERN
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class Filed:
    """The record id behind each proposal key, how many were new, and what went wrong."""

    ids: dict[str, str] = field(default_factory=dict)
    new: int = 0
    errors: str = ""


def segment(value: str, fallback: str = "general") -> str:
    """*value* as one lowercase kebab segment."""
    return _SEGMENT.sub("-", value.lower()).strip("-") or fallback


def surveyed_repo(repo_dir: str) -> str:
    """The name the surveyed repository goes by on the register."""
    return next(iter(resolve_workspace("", repo_dir)))


def file_proposals(
    logger: logging.Logger,
    root: Path,
    repo_dir: str,
    filed_by: FiledBy,
    proposals: Sequence[Proposal],
) -> Filed:
    """File each proposal that no open record of this filer already states, in one artifacts commit."""
    repo = surveyed_repo(repo_dir)
    okf = Ostler(root)
    held = {r.summary: r.id for r in okf.open_records(repo) if r.filed_by == filed_by}
    ids: dict[str, str] = {}
    new_paths: list[Path] = []
    errors = ""
    for proposal in proposals:
        known = held.get(proposal.summary)
        if known:
            logger.info("%s is already on the register as [%s]", proposal.key, known)
            ids[proposal.key] = known
            continue
        filing = okf.file_record(
            repo=repo, area=segment(proposal.area), pattern=proposal.pattern, summary=proposal.summary,
            filed_by=filed_by, symbols=proposal.symbols, body=proposal.body,
        )
        if filing.record is None or filing.path is None:
            logger.warning("%s was not filed: %s", proposal.key, filing.message)
            errors = f"{proposal.key} was not filed: {filing.message}"
            break
        held[proposal.summary] = filing.record.id
        ids[proposal.key] = filing.record.id
        new_paths.append(filing.path)
    if new_paths:
        artifacts = okf.register_root().parent
        scope = _SCOPE.sub("-", repo.lower()).strip("-.")
        subject = f"chore({scope}): file {len(new_paths)} {filed_by} records" if scope else (
            f"chore: file {len(new_paths)} {filed_by} records"
        )
        commit_paths(artifacts, subject, *(str(p.relative_to(artifacts)) for p in new_paths), verify=False)
    return Filed(ids, len(new_paths), errors)
