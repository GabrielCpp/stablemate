"""Where a workflow's own files live on disk."""

from __future__ import annotations

import importlib.resources
from pathlib import Path


class PackagedWorkflowError(RuntimeError):
    """A workflow's package cannot be used as the directory its prompts live in."""


def package_dir(package: str, *, workflow: str | None = None) -> Path:
    """Locate an importable package as a real directory on disk."""
    subject = f"workflow '{workflow}'" if workflow else f"package '{package}'"
    try:
        root = importlib.resources.files(package)
    except (ImportError, TypeError) as exc:
        raise PackagedWorkflowError(
            f"{subject}: cannot locate package '{package}': {exc}"
        ) from exc
    if not isinstance(root, Path):
        raise PackagedWorkflowError(
            f"{subject}: package '{package}' is not a real directory on disk — it "
            f"resolved to {type(root).__name__} ({root}). Workhorse renders a "
            "workflow's prompts with a filesystem template loader and keys per-node "
            "overrides on the directory name, so the package must be installed "
            "unpacked. A wheel installed by pip or uv is; a zipapp, a zip-safe egg or "
            "a namespace package split across roots is not."
        )
    if not root.is_dir():
        raise PackagedWorkflowError(
            f"{subject}: package '{package}' resolved to {root}, which is not a "
            "directory."
        )
    return root
