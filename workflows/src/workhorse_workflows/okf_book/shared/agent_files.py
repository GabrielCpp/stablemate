"""Rendering a repo's agent files from its prompt library, so a skill the library changed since the last render does not refuse a book commit."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.kit.tools import run_tool

AGENTS_CONFIG = "agents.yml"


def render_agent_files_returning_failure(root: Path) -> str:
    """Render *root*'s agent files with farrier when the repo selects any. Returns why the render failed, and empty when it did not fail."""
    if not (root / AGENTS_CONFIG).is_file():
        return ""
    try:
        result = run_tool(["farrier", "install", "--repo", str(root)], root)
    except OSError as unavailable:
        return f"farrier could not run: {unavailable}"
    if result.returncode != 0:
        return f"farrier could not render them: {(result.stderr or result.stdout).strip()}"
    return ""
