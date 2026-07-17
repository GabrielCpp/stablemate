from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, model_validator

logger = logging.getLogger(__name__)


class UnmetRequirementsError(Exception):
    """A workflow declares a tool that isn't usable. Raised before the first node."""

# The first dotted-numeric run in a `--version` line. Every CLI prints a different
# shape around it -- "git version 2.43.0", "gh version 2.45.0 (2025-07-18 ...)",
# "GNU Make 4.3", "uv 0.11.15 (x86_64-...)", "2.1.211 (Claude Code)" -- so we take
# the first thing that looks like a version and ignore the surrounding prose.
_VERSION_RE = re.compile(r"(\d+(?:\.\d+)+)")

_PROBE_TIMEOUT_S = 10


class Requirement(BaseModel):
    """One tool a workflow uses directly, and how to prove it is usable.

    Two kinds, because they are checked in genuinely different places:

    ``dist:`` a Python distribution that must be IMPORTABLE by the interpreter that
    runs script nodes. Script nodes run under ``sys.executable`` (see
    ``runner/script.py``), and workflow scripts import their tools in-process, so
    presence on ``PATH`` proves nothing here -- a pipx-isolated install gives a
    working ``ostler`` shim whose package is invisible to ``import ostler``. Keyed by
    DISTRIBUTION name, which may differ from the import name (``workhorse-agent`` vs
    ``workhorse``); dist metadata resolving in this interpreter is what implies the
    import will.

    ``cmd:`` an executable that must be on ``PATH``, invoked as a subprocess.

    This module knows no tool's name: the list is data read from ``workflow.yaml``,
    so the engine stays workflow-agnostic.
    """

    dist: str | None = None
    cmd: str | None = None
    version: str | None = None
    # Soft dependency: report but never block. For tools a workflow degrades around
    # rather than needs (groom, the telemetry sidecar, is a silent no-op when absent).
    optional: bool = False

    @model_validator(mode="after")
    def _exactly_one_kind(self) -> Requirement:
        if bool(self.dist) == bool(self.cmd):
            raise ValueError(
                "each entry in 'requires:' needs exactly one of 'dist:' or 'cmd:' "
                f"(got dist={self.dist!r}, cmd={self.cmd!r})"
            )
        if self.version is not None:
            try:
                SpecifierSet(self.version)
            except InvalidSpecifier as exc:
                raise ValueError(
                    f"requirement '{self.name}' has an invalid version specifier "
                    f"{self.version!r}: {exc}"
                ) from exc
        return self

    @property
    def name(self) -> str:
        return self.dist or self.cmd or ""

    def describe(self) -> str:
        return f"{self.name}{self.version or ''}"


def _probe_cmd_version(cmd: str) -> str | None:
    """Best-effort version of a PATH executable. None when it can't be determined.

    An unparseable or failing probe is NOT a missing tool -- the tool is on PATH, we
    just can't read its version, so a version constraint is reported as unverifiable
    rather than violated.
    """
    try:
        proc = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = f"{proc.stdout}\n{proc.stderr}"
    match = _VERSION_RE.search(text)
    return match.group(1) if match else None


def _check_one(req: Requirement) -> str | None:
    """Return a human-readable problem with this requirement, or None if satisfied."""
    if req.dist:
        try:
            found = _dist_version(req.dist)
        except PackageNotFoundError:
            # Name the interpreter and spell the fix against *it*. Anything topology
            # specific (`pipx inject <venv> ...`) would be a guess: the venv's name
            # isn't knowable from here, and a wrong hint is worse than none.
            return (
                f"{req.dist} is not installed in the interpreter that runs script "
                f"nodes. Install it there:\n"
                f"    {sys.executable} -m pip install {req.dist}{req.version or ''}"
            )
    else:
        assert req.cmd is not None
        if shutil.which(req.cmd) is None:
            return f"{req.cmd} is not on PATH"
        found = _probe_cmd_version(req.cmd)
        if found is None:
            if req.version:
                logger.warning(
                    "could not determine %s version; cannot verify %s",
                    req.cmd,
                    req.version,
                )
            return None

    if not req.version:
        return None
    try:
        parsed = Version(found)
    except InvalidVersion:
        logger.warning(
            "could not parse %s version %r; cannot verify %s",
            req.name,
            found,
            req.version,
        )
        return None
    # prereleases=True: a tool pinned to a dev/rc build should satisfy `>=x` rather
    # than be rejected on a technicality mid-unattended-run.
    if not SpecifierSet(req.version).contains(parsed, prereleases=True):
        return f"{req.name} {found} does not satisfy {req.version}"
    return None


def check_requirements(
    requires: list[Requirement], workflow_name: str
) -> list[str]:
    """Verify every tool a workflow declares. Returns the list of hard problems.

    Optional requirements are logged and excluded from the return value. The caller
    decides what an unmet hard requirement means; raising at graph load is
    deliberate -- a missing tool is deterministic and unrecoverable, so it belongs
    outside the retry/reframe/default ladder, and failing before the first node beats
    dying six nodes into an unattended run.
    """
    problems: list[str] = []
    for req in requires:
        problem = _check_one(req)
        if problem is None:
            continue
        if req.optional:
            logger.warning(
                "workflow '%s': optional requirement not met: %s",
                workflow_name,
                problem,
            )
            continue
        problems.append(problem)
    return problems
