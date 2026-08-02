"""Which workflows this machine can run, according to pipx.

A workflow is a Python distribution that binds a `workhorse-<name>` console script
(`workhorse-coder run …`). There is no entry-point group and no registry to query —
a script carries its own — so the question "what can this machine run?" is answered
by looking at what is *installed*, and `pipx list --json` is where that lives.

**The installed set is the only source of truth.** There is deliberately no
selection list in `agents.yml` to reconcile against, because a second source of
truth goes stale the moment someone `pipx install`s or uninstalls something, and a
stale list fails later and further away — as a confusing "workflow not found" rather
than at the moment the set actually changed. Discovery cannot drift from itself.

Two kinds of install, and the difference matters to whoever has to run one in a
container:

* **From PyPI** — nothing to mount. The container installs the same name and version.
* **From a local path** — a uv project on this machine. The container has to bind
  that directory read-only and install from a copy of it, which means the path is
  part of the answer.

`pipx list --json` carries all of it under `venvs.<n>.metadata.main_package`:
`package_or_url` (a PyPI name, a VCS URL, or a host path), `pip_args` (which
contains `--editable` for an editable local install), `apps` (the console scripts
the venv exposes) and `package_version`.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: A workflow's console script is `workhorse-<name>`; the suffix is the workflow.
#: This is the whole naming contract — there is no manifest listing them.
WORKFLOW_SCRIPT_PREFIX = "workhorse-"

#: Scripts matching the prefix that are not workflows. `workhorse` itself is a
#: library and binds no command, but a future one would land here rather than be
#: offered as a runnable workflow.
_NOT_WORKFLOWS = frozenset({"workhorse-agent", "workhorse-workflows"})

#: `package_or_url` values that name a remote rather than a directory. Checked by
#: prefix rather than by "does this exist on disk", so a *deleted* local path is
#: still classified as local — which is what lets it be reported as missing rather
#: than silently reclassified as a PyPI name.
_REMOTE_SCHEMES = ("git+", "http://", "https://", "hg+", "svn+", "bzr+")


@dataclass(frozen=True)
class Installed:
    """One pipx-installed distribution that provides at least one workflow."""

    #: The distribution's name, e.g. `workhorse-workflows`.
    distribution: str
    #: The workflows it provides, sorted — the `<name>` of each `workhorse-<name>`.
    workflows: tuple[str, ...]
    #: `package_or_url` verbatim: a PyPI name, a VCS URL, or a host path.
    origin: str
    version: str
    #: True when pipx installed it with `--editable`, i.e. the source is live.
    editable: bool

    @property
    def local_path(self) -> Path | None:
        """The host directory this was installed from, when it was installed from one.

        A path that no longer exists still answers here — see `missing`. Callers
        that need to *mount* it must check `missing` first.
        """
        if self.origin.startswith(_REMOTE_SCHEMES):
            return None
        # A bare PyPI name has no separator; anything with one is a path. `~` is
        # expanded because pipx records whatever the operator typed.
        candidate = Path(self.origin).expanduser()
        return candidate if candidate.is_absolute() or "/" in self.origin else None

    @property
    def missing(self) -> bool:
        """An install whose local source directory is gone.

        Worth reporting rather than ignoring: the tool still *runs* (the venv holds
        a built copy, or a `.pth` pointing at nothing), so nothing fails until a
        container tries to bind the path — at which point the error names a mount,
        not the install that went stale.
        """
        path = self.local_path
        return path is not None and not path.is_dir()


def workflows_from_apps(apps: object) -> tuple[str, ...]:
    """The workflow names among a venv's console scripts."""
    if not isinstance(apps, list):
        return ()
    return tuple(
        sorted(
            app[len(WORKFLOW_SCRIPT_PREFIX):]
            for app in apps
            if isinstance(app, str)
            and app.startswith(WORKFLOW_SCRIPT_PREFIX)
            and app not in _NOT_WORKFLOWS
            and app != WORKFLOW_SCRIPT_PREFIX
        )
    )


def parse(payload: object) -> list[Installed]:
    """Read `pipx list --json` output into the distributions that provide workflows.

    Tolerant of shape by design: this parses another tool's output, and a pipx
    upgrade that renames a key must cost a missing workflow, never a traceback in
    the middle of `make`.
    """
    if not isinstance(payload, dict):
        return []
    venvs = payload.get("venvs")
    if not isinstance(venvs, dict):
        return []

    found: list[Installed] = []
    for name, venv in venvs.items():
        if not isinstance(venv, dict):
            continue
        metadata = venv.get("metadata")
        if not isinstance(metadata, dict):
            continue
        main = metadata.get("main_package")
        if not isinstance(main, dict):
            continue
        workflows = workflows_from_apps(main.get("apps"))
        if not workflows:
            continue
        pip_args = main.get("pip_args")
        found.append(
            Installed(
                distribution=str(main.get("package") or name),
                workflows=workflows,
                origin=str(main.get("package_or_url") or ""),
                version=str(main.get("package_version") or ""),
                editable=isinstance(pip_args, list) and "--editable" in pip_args,
            )
        )
    return sorted(found, key=lambda d: d.distribution)


def discover() -> list[Installed]:
    """Ask pipx what is installed. A machine without pipx simply has no workflows.

    Every failure returns an empty list rather than raising: this is called from a
    Makefile, where the honest answer to "pipx is not installed" is "no workflows
    are discoverable", not a broken build.
    """
    try:
        result = _run(["pipx", "list", "--json"])
    except OSError:
        return []
    if result.returncode != 0:
        return []
    try:
        return parse(json.loads(result.stdout))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """The one place this module spawns anything — and so the one test seam."""
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def names(found: list[Installed]) -> list[str]:
    """Every runnable workflow name, sorted and de-duplicated.

    Two distributions providing the same workflow name is a real (if odd) state —
    a fork installed alongside the original. The name is reported once; which
    distribution's script wins is pipx's `PATH` order to settle, not this module's.
    """
    return sorted({workflow for dist in found for workflow in dist.workflows})
