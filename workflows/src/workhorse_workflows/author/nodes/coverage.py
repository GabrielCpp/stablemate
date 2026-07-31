"""Whether an epic's stories actually cover it, and the backlog it consumed.

Ported from `base-library/workflows/author/scripts/{validate-epic-coverage,prune-backlog}.py`.

The YAML handed `validate_epic_coverage` two arguments and the script read only the first;
`validate_coverage` takes the one it uses.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ostler import Ostler
from workhorse_workflows.author.nodes._blueprint import blueprint
from workhorse_workflows.author.nodes import _stubs
from workhorse_workflows.author.paths import survey_repo_root
from workhorse_workflows.author.schemas.main import Defects, Pruned

#: `ostler doctor` error codes that mean this epic's coverage or story graph is broken.
#: `unwritten-story` belongs here for the same reason `missing-story-file` does: an epic
#: whose stories are bare scaffolds covers nothing, and the deterministic gate should say
#: so without waiting for the reviewer to notice.
_COVERAGE_CODES = {
    "orphan-seed",
    "dangling-seed",
    "cross-epic-seed",
    "dangling-dependency",
    "cross-epic-dependency",
    "missing-story-file",
    "unwritten-story",
}

_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


@blueprint.node(stub=_stubs.clean)
def validate_coverage(
    logger: logging.Logger, epic_dir: str = "", repo_dir: str = ""
) -> Defects:
    """Every seed covered by a story, the story graph acyclic, every story file present.

    These are exactly what `ostler.doctor(epic=...)` computes, and the epic scope is the
    point: ostler pins its findings to the named epic, so this gate cannot evaluate the
    *wrong* epic's seeds and stories the way a whole-repo check once did.
    """
    epic_dir_rel = epic_dir.strip()
    if not epic_dir_rel:
        logger.warning("no epic_dir supplied")
        return Defects(errors="no epic_dir supplied")

    epic = Path(epic_dir_rel).name
    okf = Ostler(survey_repo_root(repo_dir))

    try:
        report = okf.doctor(epic=epic)
    except (OSError, ValueError, RuntimeError):
        logger.warning("ostler doctor for epic %s could not run", epic)
        return Defects(errors=f"ostler doctor for epic {epic} could not run")

    errors = [
        f"[{f.get('code')}] {f.get('message')}"
        for f in report.get("findings", [])
        if f.get("severity") == "error" and f.get("code") in _COVERAGE_CODES
    ]

    logger.info("epic '%s' coverage: %d error(s)", epic, len(errors))
    return Defects(ok=not errors, errors="\n".join(errors))


def _normalize(line: str) -> str:
    """A bullet line with its marker and whitespace stripped, lowercased."""
    return _BULLET_RE.sub("", line).strip().lower()


def _matches(backlog_norm: str, seed_norms: list[str]) -> bool:
    """Tolerant match: equal, or either contains the other with both at least 8 chars.

    The length floor is what keeps a short bullet ("logout") from swallowing every line
    that happens to mention it.
    """
    if not backlog_norm:
        return False
    for sn in seed_norms:
        if not sn:
            continue
        if backlog_norm == sn:
            return True
        if len(backlog_norm) >= 8 and len(sn) >= 8 and (backlog_norm in sn or sn in backlog_norm):
            return True
    return False


@blueprint.node
def prune_backlog(
    logger: logging.Logger,
    backlog: str = "docs/backlog.md",
    epic_dir: str = "",
    repo_dir: str = "",
) -> Pruned:
    """Drop the bullets a fully-authored epic consumed, so the backlog stays a worklist.

    Each of the epic's seeds records the verbatim `sourceBullet` it came from, so the
    matching is against those. Best-effort and idempotent throughout: unmatched bullets are
    left in place, and a write failure is swallowed — the run must never die because the
    backlog could not be tidied.
    """
    backlog_rel = backlog.strip() or "docs/backlog.md"
    epic_dir_rel = epic_dir.strip()
    root = survey_repo_root(repo_dir)
    backlog_path = root / backlog_rel
    epic = Path(epic_dir_rel).name if epic_dir_rel else ""

    if not backlog_path.is_file() or not epic:
        logger.info("no backlog at %s or no epic given — nothing to prune", backlog_path)
        return Pruned()

    okf = Ostler(root)
    seed_norms = [
        norm for norm in (_normalize(str(s.get("sourceBullet", ""))) for s in okf.list("seed", epic=epic)) if norm
    ]
    if not seed_norms:
        logger.info("epic '%s' has no seeds with a sourceBullet — nothing to prune", epic)
        return Pruned()

    try:
        lines = backlog_path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        logger.warning("could not read backlog %s — nothing to prune", backlog_path)
        return Pruned()

    kept: list[str] = []
    removed = 0
    remaining = 0
    for line in lines:
        is_bullet = bool(_BULLET_RE.match(line))
        if is_bullet and _matches(_normalize(line), seed_norms):
            removed += 1
            continue
        if is_bullet:
            remaining += 1
        kept.append(line)

    if removed:
        try:
            backlog_path.write_text("".join(kept), encoding="utf-8")
        except OSError:
            logger.warning(
                "could not write pruned backlog %s — best-effort, continuing", backlog_path
            )

    logger.info(
        "pruned %d bullet(s) from %s for epic '%s' (%d remaining)",
        removed,
        backlog_rel,
        epic,
        remaining,
    )
    return Pruned(removed=removed, remaining=remaining)


__all__ = ["prune_backlog", "validate_coverage"]
