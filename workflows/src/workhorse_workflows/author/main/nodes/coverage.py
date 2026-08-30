"""Whether an epic's stories actually cover it.

Ported from `base-library/workflows/author/scripts/validate-epic-coverage.py`.

The YAML handed `validate_epic_coverage` two arguments and the script read only the first;
`validate_coverage` takes the one it uses.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.main.nodes import _stubs
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Defects

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

    outcome = okf.doctor(epic=epic)
    if outcome.status == "invalid":
        logger.warning("ostler doctor for epic %s could not run: %s", epic, outcome.message)
        return Defects(errors=f"ostler doctor for epic {epic} could not run")

    errors = [
        f"[{f.get('code')}] {f.get('message')}"
        for f in outcome.data.get("findings", [])
        if f.get("severity") == "error" and f.get("code") in _COVERAGE_CODES
    ]

    logger.info("epic '%s' coverage: %d error(s)", epic, len(errors))
    return Defects(ok=not errors, errors="\n".join(errors))


__all__ = ["validate_coverage"]
