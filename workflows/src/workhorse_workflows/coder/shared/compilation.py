"""Compile the QA context packet the docs and QA flows share into a plan, and read what it refuses."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler.qa.compile import Compilation, compile_plan_gaps
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.docs import CONTEXT_FILE
from workhorse_workflows.coder.shared.schemas.docs import CompileGaps
from workhorse_workflows.kit import find_docs_root, load_json
from ostler.qa.readiness import defect_gaps, format_gap


def compile_packet(spec_root: Path, story: str, logger: logging.Logger) -> Compilation | None:
    """What compiling `<spec_root>/qa-okf-context.json` gave, or None when the packet cannot be read."""
    packet = load_json(spec_root / CONTEXT_FILE, CONTEXT_FILE, logger)
    if not packet:
        return None
    try:
        return compile_plan_gaps(packet, story=story)
    except ValueError as exc:
        logger.warning("the QA context cannot be compiled: %s", exc)
        return None


@blueprint.node
def compile_gaps(
    logger: logging.Logger,
    spec_dir: str = "",
    story: str = "",
    pages: tuple[str, ...] = (),
    repo_dir: str = "",
) -> CompileGaps:
    """The defect gaps the book's compile reports on the pages the story touched, as `<code> <ref>: <message>` lines."""
    spec = Path(spec_dir)
    spec_root = spec if spec.is_absolute() else Path(find_docs_root(repo_dir)) / spec
    compiled = compile_packet(spec_root, story, logger)
    gaps = [format_gap(gap) for gap in defect_gaps(compiled.gaps if compiled else [], pages)]
    logger.info("the book compiles with %d defect gap(s) on the story's pages", len(gaps))
    return CompileGaps(gaps=gaps)


__all__ = ["compile_gaps", "compile_packet"]
