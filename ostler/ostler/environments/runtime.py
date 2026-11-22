"""Bring a rendered copy up, read its addresses, and tear it down, through docker compose."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from platformdirs import user_state_dir

from ostler._vendor.stablemate_core import books, config
from ostler.environments.render import COMPOSE_FILE, SHARED, Copy

HOME_ENV = "OSTLER_ENV_HOME"
HOLDER_ENV = "STABLEMATE_LEASE_HOLDER"
MANIFEST = "copy.json"
ADDRESSES = "addresses.json"
SECRETS_DIR = "secrets"
IDLE_AFTER = timedelta(hours=24)
PORT_INTERVAL = 1.0
PORT_TIMEOUT = 2.0
PORT_FLOOR = 5.0
_PROJECT_CHARS = re.compile(r"[^a-z0-9_-]+")
_PUBLISHED = re.compile(r":(\d+)->")
_OCCUPANT_FORMAT = "\t".join([
    "{{.Names}}", '{{.Label "com.docker.compose.project"}}',
    '{{.Label "stablemate.ostler.service"}}', "{{.Ports}}"])


class Runner(Protocol):
    """Runs one command and returns its outcome, so a test can stand in for docker."""

    def __call__(
        self, argv: Sequence[str], *, capture: bool, stdin: str | None = None,
    ) -> subprocess.CompletedProcess[str]: ...


def run_command(
    argv: Sequence[str], *, capture: bool, stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), capture_output=capture, text=True, check=False, input=stdin)


def home() -> Path:
    """Where every copy's directory lives on this machine."""
    override = os.environ.get(HOME_ENV, "")
    if override:
        return Path(override)
    return Path(user_state_dir("stablemate")) / "ostler" / "environments"


def checkout_home(repo: Path) -> Path:
    """The main checkout of the git repository rooted at *repo*, which every worktree of it shares."""
    try:
        dot_git = repo / ".git"
        if dot_git.is_dir() or not dot_git.is_file():
            return repo
        text = dot_git.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir:"):
            return repo
        gitdir = repo / text.removeprefix("gitdir:").strip()
        common = gitdir / "commondir"
        if not common.is_file():
            return repo
        return (gitdir / common.read_text(encoding="utf-8").strip()).resolve().parent
    except OSError:
        return repo


def copy_owner(repo: Path, code: Path | None = None) -> str:
    """The name a copy of the stack at *repo* carries: the code repository's, or its workspace's, when *repo* is the artifacts folder and *code* is a checkout outside it; else the folder's."""
    if code is not None and books.namespaced(repo) and not books.namespaced(code):
        try:
            workspace = config.run_workspace(code)
        except ValueError:
            workspace = ""
        return workspace or config.repository_name(code)
    return checkout_home(repo).name


def copy_for(repo: Path, name: str = SHARED, code: Path | None = None) -> Copy:
    """The copy *name* of the stack the repo at *repo* declares, as seen from the code checkout *code*."""
    project = _PROJECT_CHARS.sub("-", f"{copy_owner(repo, code)}-{name}".lower()).strip("-_")
    return Copy(name=name, project=project, directory=home() / project)


def copies(repo: Path, code: Path | None = None) -> list[Copy]:
    """Every copy of *repo*'s stack this machine holds a directory for, those of *code*'s product when it is given."""
    found = [copy for copy, manifest in held_copies() if manifest.get("repo") == str(checkout_home(repo))]
    if code is None or not (books.namespaced(repo) and not books.namespaced(code)):
        return found
    return [copy for copy in found if copy.project == copy_for(repo, copy.name, code).project]


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


def hold(repo: Path, name: str, pid: int, code: Path | None = None) -> bool:
    """Name the process *pid* as the holder of *repo*'s copy *name*; False when the copy does not exist."""
    copy = copy_for(repo, name, code)
    manifest = read_manifest(copy.directory)
    if not manifest:
        return False
    write_manifest(copy, {**manifest, "holder": holder_stamp(pid)})
    return True


def worktree_of(cwd: Path) -> str:
    """The top level of the git worktree *cwd* stands in, or empty outside one."""
    try:
        done = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, check=False)
    except OSError:
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def touch_used(directory: Path) -> None:
    """Record now as the last use of the copy held in *directory*; a copy with no manifest, or an unwritable one, is left alone."""
    try:
        manifest = read_manifest(directory)
        if not manifest or directory.parent != home():
            return
        manifest["used_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        (directory / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    except OSError:
        return


def _listed_worktrees(repo: Path) -> set[str] | None:
    try:
        done = subprocess.run(["git", "-C", str(repo), "worktree", "list", "--porcelain"],
                              capture_output=True, text=True, check=False)
    except OSError:
        return None
    if done.returncode != 0:
        return None
    return {line.removeprefix("worktree ").strip() for line in done.stdout.splitlines()
            if line.startswith("worktree ")}


def orphaned(manifest: Mapping[str, object]) -> bool:
    """Whether the worktree a copy records is gone: no directory, and no entry in its repo's worktree list."""
    recorded = manifest.get("worktree")
    repo = manifest.get("repo")
    if not isinstance(recorded, str) or not recorded or not isinstance(repo, str):
        return False
    tree = Path(recorded)
    if tree.is_dir() or not tree.parent.is_dir() or not Path(repo).is_dir():
        return False
    listed = _listed_worktrees(Path(repo))
    return listed is not None and recorded not in listed


def used_ago(manifest: Mapping[str, object], now: datetime | None = None) -> timedelta | None:
    """How long ago the copy was last used, or None when its manifest records no use."""
    stamp = manifest.get("used_at")
    if not isinstance(stamp, str):
        return None
    try:
        then = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return (now or datetime.now(UTC)) - then.astimezone(UTC) if then.tzinfo else None


def idle(manifest: Mapping[str, object], now: datetime | None = None) -> bool:
    """Whether the copy went unused for longer than `IDLE_AFTER` and no live run holds it."""
    ago = used_ago(manifest, now)
    if ago is None or ago <= IDLE_AFTER:
        return False
    holder = manifest.get("holder")
    return not (isinstance(holder, dict) and holder.get("pid")) or not holder_alive(holder)


def release_holder(repo: Path, name: str, pid: int, code: Path | None = None) -> bool:
    """Clear the holder of *repo*'s copy *name* when it is the process *pid*, so the copy outlives the run."""
    copy = copy_for(repo, name, code)
    manifest = read_manifest(copy.directory)
    if not manifest or manifest.get("holder") != holder_stamp(pid):
        return False
    write_manifest(copy, {**manifest, "holder": {}})
    return True


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
    """The env files the copy's last `up` recorded for compose, those that still exist."""
    listed = read_manifest(copy.directory).get("env_files")
    found = [Path(str(item)) for item in listed] if isinstance(listed, list) else []
    return [path for path in found if path.is_file()]


def exec_prefix(copy: Copy) -> list[str]:
    """The command the copy's last `up` recorded to run compose under, empty when none."""
    listed = read_manifest(copy.directory).get("exec_prefix")
    return [str(item) for item in listed] if isinstance(listed, list) else []


@dataclass
class Compose:
    """docker compose, pointed at one copy's project, files and secrets."""

    copy: Copy
    runner: Runner = run_command

    def argv(self, args: Sequence[str]) -> list[str]:
        base = [*exec_prefix(self.copy), "docker", "compose", "--project-name", self.copy.project,
                "--project-directory", str(self.copy.directory),
                "--file", str(self.copy.directory / COMPOSE_FILE)]
        for env_file in env_files(self.copy):
            base += ["--env-file", str(env_file)]
        return [*base, *args]

    def run(self, args: Sequence[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
        return self.runner(self.argv(args), capture=capture)

    def up(
        self, *, wait_seconds: int, services: Sequence[str] = (), capture: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return self.run(["up", "--detach", "--build", "--remove-orphans", "--wait",
                         "--wait-timeout", str(wait_seconds), *services], capture=capture)

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


@dataclass(frozen=True)
class ProjectStates:
    """What `docker compose ls` said of every compose project, or why it said nothing."""

    projects: Mapping[str, str]
    error: str = ""

    def of(self, project: str) -> str:
        """`running` when any container of the project runs, `stopped` when none does, `unknown` when docker could not say."""
        if self.error:
            return "unknown"
        return "running" if "running(" in self.projects.get(project, "") else "stopped"

    def running(self, project: str) -> bool:
        return self.of(project) == "running"


def project_states(runner: Runner = run_command) -> ProjectStates:
    """Ask docker once which compose projects have a running container. A status line such as `exited(3), running(7)` is running."""
    try:
        outcome = runner(["docker", "compose", "ls", "--all", "--format", "json"], capture=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return ProjectStates({}, f"docker compose ls failed: {exc}")
    if outcome.returncode != 0:
        detail = (outcome.stderr or "").strip()
        return ProjectStates({}, f"docker compose ls exited {outcome.returncode}" + (f": {detail}" if detail else ""))
    try:
        rows = json.loads(outcome.stdout or "[]")
    except json.JSONDecodeError:
        return ProjectStates({}, "docker compose ls printed no JSON")
    if not isinstance(rows, list):
        return ProjectStates({}, "docker compose ls printed no list")
    return ProjectStates({str(row.get("Name", "")): str(row.get("Status", "")) for row in rows
                          if isinstance(row, dict)})


@dataclass(frozen=True)
class Occupant:
    """A running container that publishes a host port: its name, its compose project and its service."""

    container: str
    project: str
    service: str


def port_occupants(runner: Runner = run_command) -> dict[int, Occupant]:
    """Each host port a running container publishes, with that container."""
    outcome = runner(["docker", "ps", "--format", _OCCUPANT_FORMAT], capture=True)
    if outcome.returncode != 0:
        return {}
    found: dict[int, Occupant] = {}
    for line in outcome.stdout.splitlines():
        name, project, service, ports = (line.split("\t") + ["", "", "", ""])[:4]
        for port in _PUBLISHED.findall(ports):
            found[int(port)] = Occupant(name, project, service)
    return found


def port_free(port: int) -> bool:
    """Whether a process on this machine could bind *port* on the loopback address."""
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def accepts_connection(host: str, port: int) -> bool:
    """Whether a TCP connection to *host* on *port* is accepted now."""
    try:
        with socket.create_connection((host, port), timeout=PORT_TIMEOUT):
            return True
    except OSError:
        return False


port_probe = accepts_connection


def await_ports(targets: Mapping[str, tuple[str, int]], deadline: float) -> str | None:
    """Wait until every `name: (host, port)` accepts a connection once; the first name still refusing at *deadline* (a `time.monotonic` value, with a floor of `PORT_FLOOR` seconds from now), or None."""
    deadline = max(deadline, time.monotonic() + PORT_FLOOR)
    waiting = dict(targets)
    while True:
        waiting = {name: at for name, at in waiting.items() if not port_probe(*at)}
        if not waiting:
            return None
        if time.monotonic() >= deadline:
            return next(iter(waiting))
        time.sleep(PORT_INTERVAL)
