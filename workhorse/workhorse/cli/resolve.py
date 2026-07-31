"""Resolving a workflow NAME to the installed `Registry` it names.

Shared by `run` and `dot`, which both take a workflow the same way and must report an
unknown one identically — a name that resolves for one and not the other would be the
CLI disagreeing with itself.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from workhorse.packaged import (
    PackagedWorkflowError,
    find_packaged_workflow,
    installed_workflow_names,
)
from workhorse.pyflow.registry import Registry


def packaged_registry(spec: str) -> Registry:
    """The installed Python :class:`Registry` a workflow name resolves to.

    A name resolves in exactly one place: an installed distribution registering it in
    the ``workhorse.workflows`` entry-point group, whose entry point is a ``Registry``.
    There is no second mechanism. Until the YAML front-end was removed a name could
    also name a `workflow.yaml` under a library layer, and a path could be passed
    verbatim; both are gone with the loader that read them, so the errors below say so
    rather than reporting the name as merely unknown."""
    try:
        packaged = find_packaged_workflow(spec)
    except PackagedWorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if packaged is None:
        known = ", ".join(sorted(installed_workflow_names())) or "(none installed)"
        hint = (
            "\nWorkflows are Python packages now, not workflow.yaml files — a path is "
            "not a workflow.\n"
            if looks_like_path(spec)
            else ""
        )
        print(
            f"error: no workflow named '{spec}' is installed.{hint}"
            f"Installed workflows: {known}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        target = packaged.load()
    except PackagedWorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(target, Registry):
        print(
            f"error: workflow '{packaged.name}' resolves to {packaged.origin}, whose "
            f"entry point is a {type(target).__name__}, not a `Registry`.\n"
            f"Check what '{packaged.value}' actually points at.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Ask for the directory now, while the operator is still being told about
    # resolution. `Registry.directory` is what refuses a zip-imported package, and
    # deferring it to the first prompt render turns "this wheel is packed wrong" into a
    # TemplateNotFound several nodes into a run.
    try:
        target.directory()
    except PackagedWorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    return target


def looks_like_path(spec: str) -> bool:
    """Whether a ``--workflow`` value was written as a path rather than a bare name."""
    return (
        os.sep in spec
        or (os.altsep is not None and os.altsep in spec)
        or spec.endswith((".yaml", ".yml"))
        or Path(spec).exists()
    )
