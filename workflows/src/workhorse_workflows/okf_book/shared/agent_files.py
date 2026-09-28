"""Rendering a repo's agent files from its prompt library, so a skill the library changed since the last render does not refuse a book commit."""
from __future__ import annotations

import logging
from pathlib import Path

from workhorse_workflows.kit.tools import run_tool

AGENTS_CONFIG = "agents.yml"


def render_agent_files(root: Path, logger: logging.Logger) -> None:
    """Render *root*'s agent files with farrier when the repo selects any. A render that fails is logged, and the commit's hook names what is still wrong."""
    if not (root / AGENTS_CONFIG).is_file():
        return
    try:
        result = run_tool(["farrier", "install", "--repo", str(root)], root)
    except OSError as unavailable:
        logger.warning("farrier could not run to render the agent files: %s", unavailable)
        return
    if result.returncode != 0:
        logger.warning("farrier could not render the agent files: %s", (result.stderr or result.stdout).strip())
