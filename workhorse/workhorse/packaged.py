"""Workflows that arrive as an installed Python distribution.

A workflow reaches workhorse one of two ways: as a ``workflow.yaml`` under a library
directory (``_library_layers`` in :mod:`workhorse.main`), or as a package that
advertises itself in the ``workhorse.workflows`` entry-point group::

    [project.entry-points."workhorse.workflows"]
    research = "workhorse_workflows.research.workflow:workflow"

This module owns the second. It knows nothing about any particular workflow — it
maps a NAME to the package that claims it, and hands back that package's directory
on disk.

**Why a directory and not a Traversable.** Everything downstream of resolution
treats a workflow as a folder: Jinja's ``FileSystemLoader`` is rooted at it, and the
per-node flavor override keys on its ``.name``. Neither can read a zip. A wheel
unpacked into site-packages (what pip and uv do) satisfies this; a zipapp or a
zip-safe egg does not — and the failure, left alone, surfaces as a
``TemplateNotFound`` deep inside a run rather than at resolution. So the check is
here, at the seam, and it is loud.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.resources
from dataclasses import dataclass
from pathlib import Path

#: The entry-point group a distribution registers its workflows in. Points at the
#: ``Workflow`` object rather than the console-script entry function: discovery needs
#: the registry, not the callable.
ENTRY_POINT_GROUP = "workhorse.workflows"


class PackagedWorkflowError(RuntimeError):
    """A workflow's entry point exists but cannot be used.

    Always the operator's problem to fix (a broken install, a zip-imported package,
    two distributions claiming one name), never a recoverable run-time condition —
    callers turn it into a CLI error and exit."""


@dataclass(frozen=True)
class PackagedWorkflow:
    """One ``workhorse.workflows`` entry point, resolved lazily.

    Constructing this touches nothing: it records what the metadata said. Importing
    the module happens in :meth:`load`, and locating the directory in
    :meth:`workflow_dir` — so enumerating every installed workflow (for an error
    message, say) never imports anybody's code."""

    name: str
    #: The raw entry-point value, ``"package.module:attribute"``.
    value: str
    #: The distribution that registered it, when the metadata carries one.
    distribution: str | None = None

    @property
    def module(self) -> str:
        return self.value.partition(":")[0]

    @property
    def attribute(self) -> str:
        return self.value.partition(":")[2]

    @property
    def origin(self) -> str:
        """A short 'who shipped this' string for error messages."""
        return f"{self.value} ({self.distribution})" if self.distribution else self.value

    def load(self) -> object:
        """Import the module and return the entry point's target object."""
        try:
            module = importlib.import_module(self.module)
        except ImportError as exc:
            raise PackagedWorkflowError(
                f"workflow '{self.name}' is registered as {self.origin} but its module "
                f"cannot be imported: {exc}"
            ) from exc
        if not self.attribute:
            return module
        obj: object = module
        for part in self.attribute.split("."):
            try:
                obj = getattr(obj, part)
            except AttributeError as exc:
                raise PackagedWorkflowError(
                    f"workflow '{self.name}' is registered as {self.origin} but "
                    f"'{self.attribute}' is not defined there"
                ) from exc
        return obj

    def workflow_dir(self) -> Path:
        """The workflow's own directory: the package the entry-point module lives in.

        ``workhorse_workflows.research.workflow:workflow`` resolves to the
        ``research/`` directory, which is what holds ``prompts/`` and (while the YAML
        engine still runs them) ``workflow.yaml``."""
        package, sep, _ = self.module.rpartition(".")
        if not sep:
            raise PackagedWorkflowError(
                f"workflow '{self.name}' is registered as {self.origin}, a top-level "
                "module with no package around it. The entry point must name a module "
                "inside the workflow's own package (e.g. "
                "'myworkflows.research.workflow:workflow'), because the package "
                "directory is the workflow directory."
            )
        return package_dir(package, workflow=self.name)


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


def _entry_points() -> list[importlib.metadata.EntryPoint]:
    """Every installed ``workhorse.workflows`` entry point (the patch seam in tests)."""
    return list(importlib.metadata.entry_points(group=ENTRY_POINT_GROUP))


def _distribution_name(entry_point: importlib.metadata.EntryPoint) -> str | None:
    dist = getattr(entry_point, "dist", None)
    if dist is None:
        return None
    name = getattr(dist, "name", None)
    return name if isinstance(name, str) else None


def iter_packaged_workflows() -> list[PackagedWorkflow]:
    """Every installed packaged workflow, name-sorted.

    Duplicate registrations of one name are only an error when they disagree: the same
    distribution appearing twice on ``sys.path`` is a path quirk, two distributions
    claiming ``coder`` is an ambiguity about which code runs."""
    found: dict[str, PackagedWorkflow] = {}
    for entry_point in _entry_points():
        candidate = PackagedWorkflow(
            name=entry_point.name,
            value=entry_point.value,
            distribution=_distribution_name(entry_point),
        )
        previous = found.get(candidate.name)
        if previous is None:
            found[candidate.name] = candidate
        elif previous.value != candidate.value:
            raise PackagedWorkflowError(
                f"workflow '{candidate.name}' is registered twice, by "
                f"{previous.origin} and {candidate.origin}. Uninstall one — workhorse "
                "will not guess which was meant."
            )
    return [found[name] for name in sorted(found)]


def find_packaged_workflow(name: str) -> PackagedWorkflow | None:
    """The installed workflow registered under ``name``, or None."""
    for workflow in iter_packaged_workflows():
        if workflow.name == name:
            return workflow
    return None
