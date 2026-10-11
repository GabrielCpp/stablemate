"""Bring a rendered copy up, read its addresses, and tear it down, through docker compose."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from platformdirs import user_state_dir

from ostler.environments.render import COMPOSE_FILE, SHARED, Copy

HOME_ENV = "OSTLER_ENV_HOME"
HOLDER_ENV = "STABLEMATE_LEASE_HOLDER"
MANIFEST = "copy.json"
ADDRESSES = "addresses.json"
SECRETS_DIR = "secrets"
_PROJECT_CHARS = re.compile(r"[^a-z0-9_-]+")


class Runner(Protocol):
    """Runs one command and returns its outcome, so a test can stand in for docker."""

    def __call__(self, argv: Sequence[str], *, capture: bool) -> subprocess.CompletedProcess[str]: ...


def run_command(argv: Sequence[str], *, capture: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), capture_output=capture, text=True, check=False)


def home() -> Path:
    """Where every copy's directory lives on this machine."""
    override = os.environ.get(HOME_ENV, "")
    if override:
        return Path(override)
    return Path(user_state_dir("stablemate")) / "ostler" / "environments"


def copy_for(repo: Path, name: str = SHARED) -> Copy:
    """The copy *name* of the stack the repo at *repo* declares."""
    project = _PROJECT_CHARS.sub("-", f"{repo.name}-{name}".lower()).strip("-_")
    return Copy(name=name, project=project, directory=home() / project)


def checkout_name(repo: Path) -> str:
    """The name of the main checkout *repo* belongs to, the same from any of its worktrees."""
    marker = repo / ".git"
    if not marker.is_file():
        return repo.resolve().name
    gitdir = Path(marker.read_text().removeprefix("gitdir:").strip())
    if not gitdir.is_absolute():
        gitdir = repo / gitdir
    common = gitdir / "commondir"
    if common.is_file():
        gitdir = gitdir / common.read_text().strip()
    return gitdir.resolve().parent.name


def copies(repo: Path) -> list[Copy]:
    """Every copy of *repo*'s stack this machine holds a directory for."""
    return [copy for copy, manifest in held_copies() if manifest.get("repo") == str(repo)]


def read_manifest(directory: Path) -> dict[str, object]:
    try:
        raw = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def write_manifest(copy: Copy, manifest: dict[str, object]) -> Path:
    target = copy.directory / MANIFEST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def holder_from_env() -> int | None:
    """The process a command run under a lease names as the lease's holder, if any."""
    raw = os.environ.get(HOLDER_ENV, "").strip()
    return int(raw) if raw.isdigit() else None


def process_started(pid: int) -> str:
    """When the process *pid* started, in clock ticks since boot, or empty where unreadable."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return ""
    fields = stat.rpartition(")")[2].split()
    return fields[19] if len(fields) > 19 else ""


def holder_stamp(pid: int) -> dict[str, object]:
    """What a manifest records of the process holding a copy, so a reused pid does not pass for it."""
    return {"pid": pid, "started": process_started(pid)}


def holder_alive(holder: object) -> bool:
    """Whether the process a manifest records as the holder still runs; a copy with none is kept."""
    if not isinstance(holder, dict):
        return True
    pid = holder.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    started = holder.get("started")
    current = process_started(pid)
    return not (started and current and current != started)


def held_copies() -> list[tuple[Copy, dict[str, object]]]:
    """Every copy on this machine, of any repo, with its manifest."""
    root = home()
    if not root.is_dir():
        return []
    found: list[tuple[Copy, dict[str, object]]] = []
    for directory in sorted(root.iterdir()):
        manifest = read_manifest(directory)
        if manifest:
            found.append((Copy(name=str(manifest.get("copy", "")), project=directory.name,
                               directory=directory), manifest))
    return found


def env_files(copy: Copy) -> list[Path]:
    """The rendered secrets files compose reads `${VAR}` values from, one per book."""
    directory = copy.directory / SECRETS_DIR
    return sorted(directory.glob("*.env")) if directory.is_dir() else []


@dataclass
class Compose:
    """docker compose, pointed at one copy's project, files and secrets."""

    copy: Copy
    runner: Runner = run_command

    def argv(self, args: Sequence[str]) -> list[str]:
        base = ["docker", "compose", "--project-name", self.copy.project,
                "--project-directory", str(self.copy.directory),
                "--file", str(self.copy.directory / COMPOSE_FILE)]
        for env_file in env_files(self.copy):
            base += ["--env-file", str(env_file)]
        return [*base, *args]

    def run(self, args: Sequence[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
        return self.runner(self.argv(args), capture=capture)

    def up(self, *, wait_seconds: int) -> subprocess.CompletedProcess[str]:
        return self.run(["up", "--detach", "--build", "--remove-orphans", "--wait",
                         "--wait-timeout", str(wait_seconds)])

    def down(self, *, keep_data: bool) -> subprocess.CompletedProcess[str]:
        args = ["down", "--remove-orphans"]
        if not keep_data:
            args.append("--volumes")
        return self.run(args)

    def port(self, service: str, port: int) -> str:
        """The host `address:port` compose published *service*'s *port* on, or empty."""
        outcome = self.run(["port", service, str(port)], capture=True)
        return outcome.stdout.strip().splitlines()[0] if outcome.returncode == 0 and outcome.stdout.strip() else ""


def host_url(scheme: str, published: str) -> str:
    """The URL a client on this machine reaches a published `host:port` at."""
    _, _, port = published.rpartition(":")
    return f"{scheme}://localhost:{port}"


def remove(copy: Copy) -> None:
    """Delete the copy's directory, its rendered secrets included."""
    if copy.directory.is_dir() and copy.directory.parent == home():
        shutil.rmtree(copy.directory)


def remove_secrets(copy: Copy) -> None:
    """Delete the copy's rendered secrets and keep the rest, so a later `down` can drop its data."""
    directory = copy.directory / SECRETS_DIR
    if directory.is_dir() and copy.directory.parent == home():
        shutil.rmtree(directory)


def running_projects(runner: Runner = run_command) -> dict[str, str]:
    """Each compose project docker knows, with its status line."""
    outcome = runner(["docker", "compose", "ls", "--all", "--format", "json"], capture=True)
    if outcome.returncode != 0:
        return {}
    try:
        rows = json.loads(outcome.stdout or "[]")
    except json.JSONDecodeError:
        return {}
    return {str(row.get("Name", "")): str(row.get("Status", "")) for row in rows
            if isinstance(row, dict)}
