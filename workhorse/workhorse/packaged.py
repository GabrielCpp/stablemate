"""Where a workflow's own files live on disk.

A workflow reaches workhorse as an object, not a name: its distribution binds a console
script that hands its ``Registry`` straight to the CLI. Nothing is looked up, so there
is no entry-point group and no catalogue of installed workflows here — the module that
declares the script is the one that knows which workflow it is.

What survives is the question that object cannot answer for itself: *where is the
package it was defined in*, so that its `prompts/` can be read.

**Why a directory and not a Traversable.** Everything downstream treats a workflow as a
folder: Jinja's ``FileSystemLoader`` is rooted at it, and the per-node flavor override
keys on its ``.name``. Neither can read a zip. A wheel unpacked into site-packages (what
pip and uv do) satisfies this; a zipapp or a zip-safe egg does not — and the failure,
left alone, surfaces as a ``TemplateNotFound`` deep inside a run rather than at startup.
So the check is here, at the seam, and it is loud.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path


class PackagedWorkflowError(RuntimeError):
    """A workflow's package cannot be used as the directory its prompts live in.

    Always the operator's problem to fix (a broken install, a zip-imported package),
    never a recoverable run-time condition — callers turn it into a CLI error and
    exit."""


def package_dir(package: str, *, workflow: str | None = None) -> Path:
    """Locate an importable package as a real directory on disk.

    Raises :class:`PackagedWorkflowError` when the package resolves to anything that
    is not one — a zip import, a namespace package spread over several roots — rather
    than letting it fail later as a missing template."""
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
