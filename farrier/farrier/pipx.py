"""Which workflows this machine can run, according to pipx."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

WORKFLOW_SCRIPT_PREFIX = "workhorse-"

_NOT_WORKFLOWS = frozenset({"workhorse-agent", "workhorse-workflows"})

_REMOTE_SCHEMES = ("git+", "http://", "https://", "hg+", "svn+", "bzr+")


@dataclass(frozen=True)
class Installed:
    """One pipx-installed distribution that provides at least one workflow."""

    distribution: str
    workflows: tuple[str, ...]
    origin: str
    version: str
    editable: bool

    @property
    def local_path(self) -> Path | None:
        """The host directory this was installed from, when it was installed from one."""
        if self.origin.startswith(_REMOTE_SCHEMES):
            return None
        candidate = Path(self.origin).expanduser()
        return candidate if candidate.is_absolute() or "/" in self.origin else None

    @property
    def missing(self) -> bool:
        """An install whose local source directory is gone."""
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
    """Read `pipx list --json` output into the distributions that provide workflows."""
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
    """Ask pipx what is installed."""
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
    """Every runnable workflow name, sorted and de-duplicated."""
    return sorted({workflow for dist in found for workflow in dist.workflows})
