"""Decision filing — one ``decision.md`` per decision, in a folder named by its slug under the docs home's ``docs/decisions``."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from ostler._vendor.stablemate_core import config as core_config
from ostler.model import Graph
from ostler.result import Result

DECISION_FILE = "decision.md"
SECTIONS = ("Question", "Decided", "Grounded in", "Context")
SLUG_MAX = 60
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def decisions_root(graph: Graph) -> Path:
    """Where this graph's decisions live: ``docs/decisions`` under its docs home."""
    return graph.doc_roots["decisions"]


def default_repo(start: Path) -> str:
    """The repository a decision names when none is given: the member name of the repository holding *start*."""
    return core_config.repository_name(start)


def _refusal(message: str) -> Result:
    return Result(False, message)


def slug_problem(slug: str) -> str:
    """Why *slug* cannot name a folder under the docs home, or an empty string when it can."""
    if _SLUG.fullmatch(slug) and len(slug) <= SLUG_MAX:
        return ""
    return (
        f"slug {slug!r} must be short kebab-case: lowercase letters, digits and single hyphens, "
        f"at most {SLUG_MAX} characters"
    )


def add(graph: Graph, slug: str, *, repo: str, summary: str) -> Result:
    """Write the empty ``decision.md`` of *slug* and report its path; a taken slug, a slug that is not short kebab-case or an empty summary is refused."""
    problem = slug_problem(slug)
    if problem:
        return _refusal(problem)
    if not _SLUG.fullmatch(repo):
        return _refusal(f"repo {repo!r} must be one lowercase kebab segment")
    line = summary.strip()
    if not line or "\n" in line:
        return _refusal("--summary must be one non-empty line")
    folder = decisions_root(graph) / slug
    if folder.exists():
        return _refusal(
            f"decision {slug!r} already exists at {folder / DECISION_FILE}: "
            f"read it, or pick a different slug"
        )
    head = yaml.safe_dump(
        {"repo": repo, "status": "accepted", "summary": line},
        sort_keys=False, allow_unicode=True, default_flow_style=False, width=10_000,
    )
    body = "\n\n".join(f"## {title}\n" for title in SECTIONS)
    folder.mkdir(parents=True)
    target = folder / DECISION_FILE
    target.write_text(f"---\n{head}---\n\n{body}\n", encoding="utf-8")
    return Result(True, str(target), [target], entity_name=slug)
